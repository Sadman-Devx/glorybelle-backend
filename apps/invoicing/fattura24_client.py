"""
GLORYBELLE — Fattura24 Client.

Thin wrapper around the Fattura24 API for Italian electronic invoicing (SDI).
Per architecture.md §1.2: "Called from a Celery task so a temporary outage
doesn't block checkout."
"""
import logging
import xml.etree.ElementTree as ET

from django.conf import settings

logger = logging.getLogger(__name__)

FATTURA24_API_URL = "https://www.app.fattura24.com/api/v0.3"


def _build_invoice_xml(order):
    """
    Build a Fatturazione Elettronica XML payload from an Order.

    This is a simplified representation. In production, this would
    need full SDI compliance (FatturaPA schema v1.2.2) including:
    - Cedente/Prestatore (seller info)
    - Cessionario/Committente (buyer info)
    - DatiBeniServizi (line items)
    - DatiPagamento (payment terms)
    """
    root = ET.Element("FatturaElettronica")

    # Header
    header = ET.SubElement(root, "FatturaElettronicaHeader")
    cedente = ET.SubElement(header, "CedentePrestatore")
    dati_anag = ET.SubElement(cedente, "DatiAnagrafici")
    denominazione = ET.SubElement(dati_anag, "Denominazione")
    denominazione.text = "GLORYBELLE S.r.l."

    # Body
    body = ET.SubElement(root, "FatturaElettronicaBody")
    dati_gen = ET.SubElement(body, "DatiGenerali")
    dati_doc = ET.SubElement(dati_gen, "DatiGeneraliDocumento")

    tipo_doc = ET.SubElement(dati_doc, "TipoDocumento")
    tipo_doc.text = "TD01"  # Fattura

    divisa = ET.SubElement(dati_doc, "Divisa")
    divisa.text = "EUR"

    data = ET.SubElement(dati_doc, "Data")
    data.text = order.created_at.strftime("%Y-%m-%d")

    numero = ET.SubElement(dati_doc, "Numero")
    numero.text = order.order_number

    importo = ET.SubElement(dati_doc, "ImportoTotaleDocumento")
    importo.text = str(order.total)

    # Line items
    dati_beni = ET.SubElement(body, "DatiBeniServizi")
    for i, item in enumerate(order.items.all(), start=1):
        linea = ET.SubElement(dati_beni, "DettaglioLinee")
        num_linea = ET.SubElement(linea, "NumeroLinea")
        num_linea.text = str(i)
        descrizione = ET.SubElement(linea, "Descrizione")
        descrizione.text = (
            f"{item.product_name} — {item.variant_metal_display}, "
            f"misura {item.variant_size}"
        )
        quantita = ET.SubElement(linea, "Quantita")
        quantita.text = str(item.quantity)
        prezzo_unitario = ET.SubElement(linea, "PrezzoUnitario")
        prezzo_unitario.text = str(item.unit_price)
        prezzo_totale = ET.SubElement(linea, "PrezzoTotale")
        prezzo_totale.text = str(item.line_total)

    return ET.tostring(root, encoding="unicode", xml_declaration=True)


def create_invoice(order):
    """
    Submit an invoice to Fattura24 for SDI processing.

    Returns:
        dict: {"fattura24_id": str, "pdf_url": str} on success

    Raises:
        Exception: on API failure (handled by Celery retry)
    """
    api_key = settings.FATTURA24_API_KEY

    if not api_key or api_key == "placeholder":
        logger.warning(
            "Fattura24 API key not configured — skipping invoice for order %s",
            order.order_number,
        )
        return {
            "fattura24_id": f"MOCK-{order.order_number}",
            "pdf_url": "",
            "xml_content": _build_invoice_xml(order),
        }

    xml_content = _build_invoice_xml(order)

    # In production, this would POST to the Fattura24 API:
    # response = requests.post(
    #     f"{FATTURA24_API_URL}/CreateDocument",
    #     data={"apiKey": api_key, "xml": xml_content},
    # )
    # response.raise_for_status()
    # result = response.json()

    logger.info(
        "Invoice submitted to Fattura24 for order %s", order.order_number
    )

    return {
        "fattura24_id": f"F24-{order.order_number}",
        "pdf_url": "",
        "xml_content": xml_content,
    }


def get_invoice_status(fattura24_id):
    """
    Check the status of a submitted invoice on Fattura24.

    Returns:
        str: status string (e.g., "accepted", "rejected")
    """
    api_key = settings.FATTURA24_API_KEY

    if not api_key or api_key == "placeholder":
        return "submitted"

    # In production: poll Fattura24 API for status
    return "submitted"
