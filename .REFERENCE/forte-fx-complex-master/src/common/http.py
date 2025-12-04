import re
import unicodedata
from urllib.parse import quote


def make_content_disposition(filename: str, attachment: bool = True) -> str:
    """
    Returns a Content-Disposition header value that is ASCII-safe and
    preserves the UTF-8 filename via RFC 5987/6266 (filename*).
    """
    # 1) ASCII fallback: strip diacritics → ASCII; replace bad chars with '_'
    ascii_name = (
            unicodedata.normalize("NFKD", filename)
            .encode("ascii", "ignore")
            .decode("ascii")
            or "download"
    )
    ascii_name = re.sub(r'[^A-Za-z0-9._-]+', "_", ascii_name).strip("._")
    if not ascii_name:
        ascii_name = "download"

    # 2) Percent-encoded UTF-8 for filename*
    utf8_quoted = quote(filename, safe="!#$&+-.^_`|~()[]{}')(")  # keep safe punctuation

    disp_type = "attachment" if attachment else "inline"
    # Both filename= (ASCII) and filename*= (UTF-8)
    return f"{disp_type}; filename=\"{ascii_name}\"; filename*=UTF-8''{utf8_quoted}"
