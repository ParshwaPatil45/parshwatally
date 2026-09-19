import re
import frappe

from parshwa.parshwa.tally_client import send_to_tally


# ============================================================
# GET TALLY COMPANY
# ============================================================

def get_tally_company():
    settings = frappe.get_all(
        "Tally Settings",
        filters={"enabled": 1},
        fields=["tally_company"],
        limit=1
    )

    if not settings:
        frappe.throw("No enabled Tally Settings found.")

    return settings[0].tally_company


# ============================================================
# CREATE PURCHASE INVOICE IN TALLY
# ============================================================

def create_tally_purchase_invoice(invoice_name):
    invoice = frappe.get_doc("Purchase Invoice", invoice_name)

    # --------------------------------------------------------
    # Prevent duplicate Tally voucher
    # --------------------------------------------------------

    if invoice.custom_tally_voucher_id and str(invoice.custom_tally_voucher_id) != "0":
        return {
            "success": False,
            "response": (
                f"Purchase Invoice {invoice_name} "
                f"is already synced to Tally. "
                f"Tally Voucher ID: {invoice.custom_tally_voucher_id}"
            ),
            "tally_voucher_id": invoice.custom_tally_voucher_id,
        }

    tally_company = get_tally_company()
    supplier = invoice.supplier

    tally_company = get_tally_company()

    supplier = invoice.supplier

    # Remove ERPNext company suffix
    if " - " in supplier:
        supplier = supplier.split(" - ")[0]

    total_amount = invoice.grand_total

    posting_date = invoice.posting_date.strftime("%Y%m%d")

    xml_data = f"""<ENVELOPE>
<HEADER>
    <VERSION>1</VERSION>
    <TALLYREQUEST>Import</TALLYREQUEST>
    <TYPE>Data</TYPE>
    <ID>Vouchers</ID>
</HEADER>

<BODY>

<DESC>
    <STATICVARIABLES>
        <SVCURRENTCOMPANY>{tally_company}</SVCURRENTCOMPANY>
    </STATICVARIABLES>
</DESC>

<DATA>

<TALLYMESSAGE xmlns:UDF="TallyUDF">

<VOUCHER
    VCHTYPE="Purchase"
    ACTION="Create"
    OBJVIEW="Accounting Voucher View">

    <DATE>{posting_date}</DATE>

    <VOUCHERTYPENAME>Purchase</VOUCHERTYPENAME>

    <VOUCHERNUMBER>{invoice_name}</VOUCHERNUMBER>

    <REFERENCE>{invoice_name}</REFERENCE>

    <PERSISTEDVIEW>Accounting Voucher View</PERSISTEDVIEW>

    <PARTYLEDGERNAME>{supplier}</PARTYLEDGERNAME>

    <LEDGERENTRIES.LIST>

        <LEDGERNAME>{supplier}</LEDGERNAME>

        <ISDEEMEDPOSITIVE>Yes</ISDEEMEDPOSITIVE>

        <ISPARTYLEDGER>Yes</ISPARTYLEDGER>

        <AMOUNT>-{total_amount:.2f}</AMOUNT>

    </LEDGERENTRIES.LIST>


    <LEDGERENTRIES.LIST>

        <LEDGERNAME>Purchase</LEDGERNAME>

        <ISDEEMEDPOSITIVE>No</ISDEEMEDPOSITIVE>

        <AMOUNT>{total_amount:.2f}</AMOUNT>

    </LEDGERENTRIES.LIST>

</VOUCHER>

</TALLYMESSAGE>

</DATA>

</BODY>
</ENVELOPE>"""

    print("\n========== PURCHASE CREATE XML ==========")
    print(xml_data)
    print("=========================================\n")

    result = send_to_tally(xml_data)

    if not result.get("success"):
        return result

    response = result.get("response", "")

    # --------------------------------------------------------
    # CHECK CREATE FAILURE
    # --------------------------------------------------------

    if (
        "<STATUS>0</STATUS>" in response
        or "<ERRORS>1</ERRORS>" in response
        or "<CREATED>0</CREATED>" in response
    ):
        frappe.log_error(
            title=f"Tally Purchase Invoice Create Failed: {invoice_name}",
            message=response
        )

        return {
            "success": False,
            "response": response
        }

    # --------------------------------------------------------
    # GET TALLY MASTER ID
    # --------------------------------------------------------

    match = re.search(
        r"<LASTVCHID>(\d+)</LASTVCHID>",
        response
    )

    if not match:

        frappe.log_error(
            title=f"Tally Purchase Invoice Master ID Missing: {invoice_name}",
            message=response
        )

        return {
            "success": False,
            "response": response
        }

    tally_voucher_id = match.group(1)

    # --------------------------------------------------------
    # SAVE TALLY VOUCHER ID
    # --------------------------------------------------------

    frappe.db.set_value(
        "Purchase Invoice",
        invoice_name,
        "custom_tally_voucher_id",
        tally_voucher_id
    )

    # Because Tally numbering is MANUAL,
    # ERPNext invoice number becomes Tally voucher number.

    frappe.db.set_value(
        "Purchase Invoice",
        invoice_name,
        "custom_tally_vch_number",
        invoice_name
    )

    frappe.db.commit()

    print("Tally Voucher ID:", tally_voucher_id)
    print("Tally Voucher Number:", invoice_name)

    return {
        "success": True,
        "response": response,
        "tally_voucher_id": tally_voucher_id,
        "tally_voucher_number": invoice_name
    }


# ============================================================
# CANCEL PURCHASE INVOICE IN TALLY
# ============================================================

def cancel_tally_purchase_invoice(invoice_name):
    import frappe
    from parshwa.parshwa.tally_client import send_to_tally

    invoice = frappe.get_doc("Purchase Invoice", invoice_name)
    tally_company = get_tally_company()

    voucher_id = invoice.custom_tally_voucher_id

    if not voucher_id:
        return {
            "success": False,
            "response": "No Tally Voucher ID found."
        }

    posting_date = invoice.posting_date.strftime("%Y%m%d")

    xml = f"""<ENVELOPE>
<HEADER>
    <VERSION>1</VERSION>
    <TALLYREQUEST>Import</TALLYREQUEST>
    <TYPE>Data</TYPE>
    <ID>Vouchers</ID>
</HEADER>

<BODY>
<DESC>
    <STATICVARIABLES>
        <SVCURRENTCOMPANY>{tally_company}</SVCURRENTCOMPANY>
    </STATICVARIABLES>
</DESC>

<DATA>
<TALLYMESSAGE xmlns:UDF="TallyUDF">

<VOUCHER VCHTYPE="Purchase" ACTION="Alter">

    <DATE>{posting_date}</DATE>

    <VOUCHERTYPENAME>Purchase</VOUCHERTYPENAME>

    <VOUCHERNUMBER>{invoice.name}</VOUCHERNUMBER>

    <REFERENCE>{invoice.name}</REFERENCE>

    <MASTERID>{voucher_id}</MASTERID>

    <ISCANCELLED>Yes</ISCANCELLED>

</VOUCHER>

</TALLYMESSAGE>
</DATA>
</BODY>
</ENVELOPE>"""

    print("\n========== PURCHASE CANCEL XML ==========")
    print(xml)
    print("========================================\n")

    result = send_to_tally(xml)

    response = result.get("response", "")

    if "<ALTERED>1</ALTERED>" in response:
        return {"success": True, "response": response}

    frappe.log_error(
        title=f"Tally Purchase Cancel Failed: {invoice_name}",
        message=response
    )

    return {"success": False, "response": response}
# ============================================================
# DELETE PURCHASE INVOICE FROM TALLY
# ============================================================

def delete_tally_purchase_invoice(invoice):

    invoice_name = invoice.name

    tally_company = get_tally_company()

    tally_voucher_number = invoice.get(
        "custom_tally_vch_number"
    )

    if not tally_voucher_number:

        message = (
            f"No Tally Voucher Number found for "
            f"Purchase Invoice {invoice_name}"
        )

        frappe.log_error(
            title="Tally Purchase Invoice Delete Skipped",
            message=message
        )

        return {
            "success": False,
            "response": message
        }

    voucher_date = invoice.posting_date.strftime(
        "%Y%m%d"
    )

    xml_data = f"""<ENVELOPE>
<HEADER>
    <VERSION>1</VERSION>
    <TALLYREQUEST>Import</TALLYREQUEST>
    <TYPE>Data</TYPE>
    <ID>Vouchers</ID>
</HEADER>

<BODY>

<DESC>
    <STATICVARIABLES>
        <SVCURRENTCOMPANY>{tally_company}</SVCURRENTCOMPANY>
    </STATICVARIABLES>
</DESC>

<DATA>

<TALLYMESSAGE>

<VOUCHER
    DATE="{voucher_date}"
    TAGNAME="VoucherNumber"
    TAGVALUE="{tally_voucher_number}"
    VCHTYPE="Purchase"
    ACTION="Delete">
</VOUCHER>

</TALLYMESSAGE>

</DATA>

</BODY>
</ENVELOPE>"""

    print("\n========== PURCHASE DELETE XML ==========")
    print(xml_data)
    print("=========================================\n")

    result = send_to_tally(xml_data)

    response = result.get("response", "")

    if (
        "<DELETED>1</DELETED>" in response
        and "<LINEERROR>" not in response
        and "<STATUS>0</STATUS>" not in response
    ):

        return {
            "success": True,
            "response": response
        }

    frappe.log_error(
        title=f"Tally Purchase Invoice Delete Failed: {invoice_name}",
        message=response
    )

    return {
        "success": False,
        "response": response
    }