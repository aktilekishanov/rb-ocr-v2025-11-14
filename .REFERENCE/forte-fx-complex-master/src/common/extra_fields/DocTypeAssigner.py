from typing import Dict, Any, Optional, List

from src.common.logger.logger_config import get_logger

logger = get_logger("DocTypeAssigner")

class DocTypeAssigner:

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
    def _combine_confidence(*confs: Optional[float]) -> float:
        nums = [c for c in confs if isinstance(c, (int, float))]
        return float(min(nums)) if nums else 1.0

    @staticmethod
    def _merge_references(*refs_lists: Optional[List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
        merged_by_file: Dict[str, Dict[str, Any]] = {}
        for refs in refs_lists or []:
            if not refs:
                continue
            for ref in refs:
                fname = ref.get("filename") or "__unknown__"
                bucket = merged_by_file.setdefault(
                    fname, {"filename": None if fname == "__unknown__" else fname, "occurrences": []}
                )
                for occ in ref.get("occurrences", []):
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
        return [
            payload for fname, payload in merged_by_file.items()
            if not (fname == "__unknown__" and not payload["occurrences"])
        ]

    @staticmethod
    def _parse_un_value(un_raw: Optional[str]) -> Optional[int]:
        """
        Принимает значения вроде '1', '0', '1 (defaulted to 50000.01 USD)', '1 some comment'.
        Возвращает 1, 0 или None (если распарсить нельзя).
        """
        if un_raw is None:
            return None
        s = str(un_raw).strip()
        if not s:
            return None
        head = s.split()[0]
        if head in {"1", "0"}:
            return int(head)
        return None

    @staticmethod
    def _map_code_goods(is_export: bool, crosses: bool, un_value: int) -> str:
        """
        ТОВАРЫ → коды 01–08.
        UN==1 => '> 50 000 USD или суммы нет' (подлежит присвоению УН): 01/02/07/08
        UN==0 => '≤ 50 000 USD' (не подлежит присвоению УН): 03/04/05/06

        Соответствие правилам (оригинальные условия как комментарии):
        # 01 - экспорт товара, пересекает границу РК, подлежит УН: сумма > 50 000 USD* или отсутствует сумма.
        # 02 - импорт товара, пересекает границу РК, подлежит УН: сумма > 50 000 USD* или отсутствует сумма.
        # 03 - экспорт товара, пересекает границу, не подлежит УН: сумма ≤ 50 000 USD*.
        # 04 - импорт товара, пересекает границу РК, не подлежит УН: сумма ≤ 50 000 USD*.
        # 05 - экспорт товара без пересечения границы РК, не подлежит УН: сумма ≤ 50 000 USD*.
        # 06 - импорт товара без пересечения границы РК, не подлежит УН: сумма ≤ 50 000 USD*.
        # 07 - экспорт товара без пересечения границы РК, подлежит УН: сумма > 50 000 USD* или отсутствует сумма.
        # 08 - импорт товара без пересечения границы РК, подлежит УН: сумма > 50 000 USD* или отсутствует сумма.
        """
        if un_value == 1:
            if is_export and crosses:  # 01
                return "01"
            if (not is_export) and crosses:  # 02
                return "02"
            if is_export and (not crosses):  # 07
                return "07"
            return "08"  # import & no-cross
        else:
            if is_export and crosses:  # 03
                return "03"
            if (not is_export) and crosses:  # 04
                return "04"
            if is_export and (not crosses):  # 05
                return "05"
            return "06"  # import & no-cross

    @staticmethod
    def _map_code_services(is_export: bool, un_value: int) -> Optional[str]:
        """
        РАБОТЫ/УСЛУГИ → коды 09–10 относятся к случаям 'не подлежит присвоению УН' (UN==0, сумма ≤ 50 000 USD).
        # 09 - экспорт работ/услуг,
        # 10 - импорт работ/услуг,

        Если UN==1 (т.е. > 50 000 USD или суммы нет) — формально 'подлежит присвоению УН',
        но отдельного кода среди 01–10 для услуг > 50 000 USD нет → возвращаем None (залогировано).
        """

        return "09" if is_export else "10"


    @staticmethod
    def assign_doc_type(contract_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Единый блок присвоения 'Тип договора для учетной системы' с учётом поля:
        - 'Код вида валютного договора' (1 или 4 → ТОВАР; 2 → УСЛУГИ)
        - 'Тип договора' (для определения направления: импорт/экспорт; также fallback для услуги/работы по подстроке)
        - 'Пересечение РК' ('1' если пересекает границу РК, иначе '0')
        - 'Присвоение УН' (UN=1 → '>50k или суммы нет'; UN=0 → '≤50k')

        Алгоритм:
          1) Определяем направление: импорт/экспорт (по 'Тип договора').
          2) Определяем предмет: товар/услуга — в приоритете 'Код вида валютного договора':
               1 или 4 → товар; 2 → услуга; иначе — fallback по подстрокам 'УСЛУГ'/'РАБОТ'.
          3) Map:
               - GOODS → 01–08 по правилам (см. комментарии в _map_code_goods)
               - SERVICES → 09/10 только при UN==0; при UN==1 → None (нет кода в 01–10)
        """
        fields: List[Dict[str, Any]] = list(contract_data.get("fields", []))

        # --- INPUTS
        f_type   = DocTypeAssigner._find_field(fields, "Тип договора")
        f_border = DocTypeAssigner._find_field(fields, "Пересечение РК")
        f_un     = DocTypeAssigner._find_field(fields, "Присвоение УН")
        f_kind   = DocTypeAssigner._find_field(fields, "Код вида валютного договора")  # NEW

        contract_type_raw = DocTypeAssigner._unwrap(f_type.get("value")   if f_type   else None)
        border_crossing   = DocTypeAssigner._unwrap(f_border.get("value") if f_border else None) or "0"
        un_raw            = DocTypeAssigner._unwrap(f_un.get("value")     if f_un     else None)
        kind_raw          = DocTypeAssigner._unwrap(f_kind.get("value")   if f_kind   else None)  # 1/4=товар, 2=услуга

        contract_type = str(contract_type_raw) if contract_type_raw not in (None, "null", "") else None
        border_crossing = str(border_crossing)
        un_raw = str(un_raw) if un_raw not in (None, "null", "") else None

        # Нормализация kind_raw к int
        kind_val: Optional[int] = None
        if kind_raw not in (None, "null", ""):
            try:
                kind_val = int(str(kind_raw).strip())
            except Exception:
                kind_val = None

        logger.info(
            " Inputs — Тип='%s', Пересечение='%s', УН='%s', Код вида =%s",
            contract_type, border_crossing, un_raw, kind_val
        )

        contract_type_for_un: Optional[str] = None

        # --- BASIC GUARDS
        if not contract_type:
            logger.warning("Missing 'Тип договора' — cannot assign code")
            mapped_conf = DocTypeAssigner._combine_confidence(
                f_type.get("confidence") if f_type else None,
                f_border.get("confidence") if f_border else None,
                f_un.get("confidence") if f_un else None,
                f_kind.get("confidence") if f_kind else None,
            )
            merged_refs = DocTypeAssigner._merge_references(
                f_type.get("references") if f_type else [],
                f_border.get("references") if f_border else [],
                f_un.get("references") if f_un else [],
                f_kind.get("references") if f_kind else [],
            )
            fields.append({
                "name": "Тип договора для учетной системы",
                "value": [None],
                "confidence": mapped_conf,
                "references": merged_refs,
            })
            return {"fields": fields}

        ct_upper = contract_type.upper()
        crosses = (border_crossing == "1")

        # 1) направление
        is_export = "ЭКСПОРТ" in ct_upper
        is_import = "ИМПОРТ" in ct_upper
        if not (is_export or is_import):
            logger.warning("Cannot determine direction (import/export) from 'Тип договора': %s", contract_type)

        # 2) предмет (товар/услуга): ПРИОРИТЕТ — 'Код вида валютного договора'
        #    1 или 4 → товар; 2 → услуга; иначе — fallback по подстрокам 'УСЛУГ'/'РАБОТ'
        kind_is_goods: Optional[bool] = None
        if kind_val in (1, 4):
            kind_is_goods = True
        elif kind_val == 2:
            kind_is_goods = False
        else:
            # fallback по строке
            if ("УСЛУГ" in ct_upper) or ("РАБОТ" in ct_upper):
                kind_is_goods = False
            else:
                # нет явного сигнала — считаем товаром ТОЛЬКО если в формулировке нет упоминаний про услуги/работы
                kind_is_goods = True
            logger.warning(
                "Ambiguous or missing 'Код вида валютного договора' (got=%s). Fallback to heuristics → is_goods=%s",
                kind_val, kind_is_goods
            )

        # 3) UN
        un_value = DocTypeAssigner._parse_un_value(un_raw)
        if un_value is None:
            logger.warning("'Присвоение УН' is missing/unparseable — cannot map code")
        else:
            if kind_is_goods:
                if is_export or is_import:
                    contract_type_for_un = DocTypeAssigner._map_code_goods(
                        is_export=is_export, crosses=crosses, un_value=un_value
                    )
                    logger.info(
                        "Mapped ТОВАР by UN=%s, export=%s, border=%s → code=%s",
                        un_value, is_export, crosses, contract_type_for_un
                    )
                else:
                    logger.info("ТОВАР detected but direction missing — cannot derive 01–08 code.")
            else:
                if is_export or is_import:
                    contract_type_for_un = DocTypeAssigner._map_code_services(
                        is_export=is_export, un_value=un_value
                    )
                    if contract_type_for_un is None and un_value == 1:
                        logger.info(
                            "Services & UN=1 (>50k or no amount): no explicit code among 01–10 — returning None."
                        )
                    else:
                        logger.info(
                            "Mapped УСЛУГИ by UN=%s, export=%s → code=%s",
                            un_value, is_export, contract_type_for_un
                        )
                else:
                    logger.info("Services detected but direction missing — cannot derive 09/10 code.")

        # Наследуем/агрегируем уверенность и ссылки из всех задействованных полей
        mapped_conf = DocTypeAssigner._combine_confidence(
            f_type.get("confidence") if f_type else None,
            f_border.get("confidence") if f_border else None,
            f_un.get("confidence") if f_un else None,
            f_kind.get("confidence") if f_kind else None,
        )
        merged_refs = DocTypeAssigner._merge_references(
            f_type.get("references") if f_type else [],
            f_border.get("references") if f_border else [],
            f_un.get("references") if f_un else [],
            f_kind.get("references") if f_kind else [],
        )

        fields.append({
            "name": "Тип договора для учетной системы",
            "value": [contract_type_for_un] if contract_type_for_un is not None else [None],
            "confidence": mapped_conf,
            "references": merged_refs,
        })

        return {"fields": fields}
