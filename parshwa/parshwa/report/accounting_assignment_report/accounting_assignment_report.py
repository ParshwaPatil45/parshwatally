SELECT
    si.posting_date AS "Posting Date:Date:100",
    si.name AS "Invoice:Link/Sales Invoice:180",
    si.customer AS "Customer:Data:180",
    si.currency AS "Currency:Link/Currency:90",
    si.conversion_rate AS "Exchange Rate:Float:100",
    si.grand_total AS "Grand Total:Currency:120",
    si.base_grand_total AS "Company Amount:Currency:130",
    si.outstanding_amount AS "Outstanding:Currency:120",
    si.status AS "Status:Data:120"
FROM
    `tabSales Invoice` si
WHERE
    si.docstatus = 1
    AND si.posting_date BETWEEN %(from_date)s AND %(to_date)s
ORDER BY
    si.posting_date DESC