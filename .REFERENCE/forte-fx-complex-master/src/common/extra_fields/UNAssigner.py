import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime
from typing import Dict, Any, Optional, List

from src.common.logger.logger_config import get_logger

logger = get_logger("UNAssigner")

class UNAssigner:
    @staticmethod
    def convert_date_format(date_str: str) -> Optional[str]:
        """Converts date from YYYY-MM-DD to DD.MM.YYYY"""
        if not date_str or str(date_str).lower() == "null" or str(date_str).strip() == "":
            return None
        try:
            date_obj = datetime.strptime(date_str, "%Y-%m-%d")
            return date_obj.strftime("%d.%m.%Y")
        except ValueError:
            return None

    @staticmethod
    def nbrk_kurs(valuta_input: str, date: Optional[str]) -> Optional[float]:
        """
        Parse the official rate of each currency and convert it into USD.
        IMPORTANT: if `date` is None/empty -> return None without calling the API.
        """
        if not date:
            logger.info("nbrk_kurs: date is None/empty, skipping FX lookup.")
            return None

        url = f"https://nationalbank.kz/rss/get_rates.cfm?fdate={date}"

        try:
            with urllib.request.urlopen(url) as response:
                xml_data = response.read()
        except Exception as e:
            logger.error(f"Failed to fetch data for {valuta_input} on {date}: {str(e)}")
            return None

        try:
            root = ET.fromstring(xml_data)
        except ET.ParseError:
            logger.error(f"Invalid XML response for {valuta_input} on {date}")
            return None

        usd_kzt = None
        for item in root.findall("item"):
            title = item.find("title").text
            if title == "USD":
                quant = float(item.find("quant").text)
                description = float(item.find("description").text)
                usd_kzt = description / quant  # KZT per 1 USD
                break

        if usd_kzt is None:
            logger.error(f"USD rate not found for {date}")
            return None

        if valuta_input.upper() == "KZT":
            return 1 / usd_kzt  # USD per 1 KZT

        for item in root.findall("item"):
            title = item.find("title").text
            if title and title.upper() == valuta_input.upper():
                quant = float(item.find("quant").text)
                description = float(item.find("description").text)
                kzt_per_unit = description / quant
                usd_equivalent = kzt_per_unit / usd_kzt  # USD per 1 <valuta_input>
                return usd_equivalent

        logger.error(f"Currency {valuta_input} not found for {date}")
        return None

    # ---------- STRICT amount parser ----------
    @staticmethod
    def parse_amount_to_float(value: Any) -> Optional[float]:
        """
        Parse a money string into float.
        Allowed characters: digits, comma, dot.
        Handles:
          - "100.00"
          - "100,00"
          - "1,234.56"
          - "1.234,56"
          - "1234,56"
        Returns None on failure.
        """
        if value in (None, "", "null"):
            return None

        if isinstance(value, (int, float)):
            return float(value)

        s = str(value).strip()
        if not s:
            return None

        # Keep only digits, dot, comma
        s = "".join(ch for ch in s if ch.isdigit() or ch in {".", ","})
        if not s:
            return None

        has_dot = "." in s
        has_comma = "," in s

        def to_float(num_str: str) -> Optional[float]:
            try:
                return float(num_str)
            except Exception:
                return None

        if has_dot and has_comma:
            # Use the last symbol as decimal
            last_dot = s.rfind(".")
            last_comma = s.rfind(",")
            if last_dot > last_comma:
                decimal = "."
                thousands = ","
            else:
                decimal = ","
                thousands = "."
            s_norm = s.replace(thousands, "")
            s_norm = s_norm.replace(decimal, ".")
            return to_float(s_norm)

        if has_dot ^ has_comma:
            sep = "." if has_dot else ","
            parts = s.split(sep)
            if len(parts) == 1:
                return to_float(parts[0])

            if s.count(sep) > 1:
                # all but last are thousands
                int_part = "".join(parts[:-1])
                frac_part = parts[-1]
                s_norm = f"{int_part}.{frac_part}"
                return to_float(s_norm)

            before, after = parts
            if len(before) > 3 and len(after) == 3:
                # thousands separator
                s_norm = before + after
                return to_float(s_norm)
            else:
                # decimal separator
                s_norm = before + "." + after
                return to_float(s_norm)

        return to_float(s)

    # ---------- FX wrapper ----------
    @staticmethod
    def convert_to_usd(amount: float, currency: str, date_ddmmyyyy: Optional[str]) -> Optional[float]:
        """
        Convert amount in `currency` to USD using NBRK rate for given date.
        If `date_ddmmyyyy` is None/empty -> return None and DO NOT call nbrk_kurs.
        """
        if amount is None or currency is None:
            return None
        currency = str(currency).strip().upper()
        if currency == "USD":
            return float(amount)
        if not date_ddmmyyyy:
            logger.info("convert_to_usd: date is None/empty, skipping FX lookup.")
            return None

        try:
            rate_usd_per_unit = UNAssigner.nbrk_kurs(currency, date_ddmmyyyy)
        except Exception as e:
            logger.error(f"Rate fetch failed for {currency} on {date_ddmmyyyy}: {e}")
            return None
        if rate_usd_per_unit is None:
            return None
        return float(amount) * float(rate_usd_per_unit)

    # ---------- helpers ----------
    @staticmethod
    def _find_field(fields: List[Dict[str, Any]], name: str) -> Optional[Dict[str, Any]]:
        for f in fields:
            if f.get("name") == name:
                return f
        return None

    @staticmethod
    def _unwrap(value):
        if isinstance(value, list):
            return value[0] if value else None
        return value

    @staticmethod
    def _get_value(fields: List[Dict[str, Any]], name: str):
        f = UNAssigner._find_field(fields, name)
        if not f:
            return None
        return UNAssigner._unwrap(f.get("value"))

    @staticmethod
    def _combine_confidence(*confs: Optional[float]) -> float:
        nums = [c for c in confs if isinstance(c, (int, float))]
        return float(min(nums)) if nums else 1.0

    @staticmethod
    def _merge_references(*refs_lists: Optional[List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
        merged_by_file: Dict[str, Dict[str, Any]] = {}
        for refs in refs_lists:
            if not refs:
                continue
            for ref in refs:
                fname = ref.get("filename")
                occs = ref.get("occurrences", [])
                if not fname:
                    fname = "__unknown__"
                bucket = merged_by_file.setdefault(
                    fname, {"filename": None if fname == "__unknown__" else fname, "occurrences": []}
                )
                for occ in occs:
                    page = occ.get("page")
                    bbox = occ.get("bbox")
                    key = (page, tuple(bbox) if isinstance(bbox, list) else None)
                    if not any(
                        (o.get("page"), tuple(o.get("bbox")) if isinstance(o.get("bbox"), list) else None) == key
                        for o in bucket["occurrences"]
                    ):
                        bucket["occurrences"].append(
                            {"page": page, "bbox": bbox[:] if isinstance(bbox, list) else bbox}
                        )
        result = []
        for fname, payload in merged_by_file.items():
            if fname == "__unknown__" and not payload["occurrences"]:
                continue
            result.append(payload)
        return result

    # ---------- main logic ----------
    @staticmethod
    def assign_account_number(contract_data: Dict[str, Any]) -> Dict[str, Any]:
        """Assigns account number with default sum logic if absent."""
        fields: List[Dict[str, Any]] = list(contract_data.get("fields", []))

        f_amount = UNAssigner._find_field(fields, "Сумма договора")
        f_currency = UNAssigner._find_field(fields, "Валюта договора")
        f_type = UNAssigner._find_field(fields, "Тип договора")
        f_date = UNAssigner._find_field(fields, "Дата валютного договора")
        f_border = UNAssigner._find_field(fields, "Пересечение РК")
        f_amount_kind = UNAssigner._find_field(fields, "Вид суммы договора")

        amount_raw = UNAssigner._unwrap(f_amount.get("value") if f_amount else None)
        currency = UNAssigner._unwrap(f_currency.get("value") if f_currency else None)
        contract_type = UNAssigner._unwrap(f_type.get("value") if f_type else None)
        date_iso = UNAssigner._unwrap(f_date.get("value") if f_date else None)
        border_crossing = UNAssigner._unwrap(f_border.get("value") if f_border else None) or "0"
        amount_kind = UNAssigner._unwrap(f_amount_kind.get("value") if f_amount_kind else None)

        currency = str(currency) if currency not in (None, "null", "") else None
        contract_type = str(contract_type) if contract_type not in (None, "null", "") else None
        date_iso = str(date_iso) if date_iso not in (None, "null", "") else None
        border_crossing = str(border_crossing)
        amount_kind = str(amount_kind) if amount_kind not in (None, "null", "") else None

        # Convert JSON amount to float first
        amount = UNAssigner.parse_amount_to_float(amount_raw)
        converted_date = UNAssigner.convert_date_format(date_iso) if date_iso else None

        un_value = None
        un_comment = None
        amount_usd = None

        if amount_kind and amount_kind.strip().lower() == "ориентировочная" and (amount is None):
            un_value = 1
            un_comment = None
            logger.info("Assigned УН=1 due to 'ориентировочная' amount type and amount = None")
        else:
            # If date/currency/type is missing -> do NOT call nbrk_kurs; leave UN as None.
            if not date_iso or not currency or not contract_type:
                un_value = None
                logger.warning("Missing critical field(s): date, currency, or contract type — УН not assigned")
            elif contract_type.upper() not in ["ИМПОРТ", "ЭКСПОРТ"]:
                un_value = 0
                logger.info(f"Contract type {contract_type} is not eligible — УН=0")
            elif amount is None:
                # Only attempt default sum when we have a converted date (guarded inside nbrk_kurs too)
                try:
                    kurs = UNAssigner.nbrk_kurs("USD", converted_date) if converted_date else None
                    if kurs:
                        default_usd = 50000.01
                        default_amount = default_usd / kurs if currency.upper() != "USD" else default_usd
                        amount = float(f"{default_amount:.2f}")
                        un_value = 1
                        un_comment = f"(defaulted to {default_usd:.2f} USD)"
                        logger.info(f"Sum defaulted: {amount} {currency} {un_comment}")
                    else:
                        logger.warning(f"No kurs available for USD on {converted_date}, default sum not applied")
                except Exception as e:
                    logger.error(f"Error applying default sum: {e}")
            else:
                if currency.upper() == "USD":
                    amount_usd = amount
                else:
                    amount_usd = UNAssigner.convert_to_usd(amount, currency, converted_date)
                    logger.info(f"Original amount {amount} {currency.upper()} converted to {amount_usd} USD")

                if amount_usd is not None and amount_usd > 50000.0:
                    un_value = 1
                    logger.info(f"Amount {amount_usd:.2f} USD exceeds threshold — УН=1")
                else:
                    un_value = 0
                    logger.info(f"Amount {amount_usd:.2f} USD does not exceed threshold — УН=0")

        amount_conf = f_amount.get("confidence") if f_amount else None
        un_confidence = UNAssigner._combine_confidence(amount_conf)
        amount_refs = f_amount.get("references") if f_amount else []
        un_references = UNAssigner._merge_references(amount_refs)

        un_value_str = (f"{un_value} {un_comment}" if un_comment else ("" if un_value is None else str(un_value)))


        fields.append(
            {
                "name": "Присвоение УН",
                "value": [un_value_str] if un_value_str != "" else [],
                "confidence": un_confidence,
                "references": un_references,
            }
        )

        logger.info(f"Final assigned УН: {un_value_str if un_value_str else 'None'}")

        return {"fields": fields}
