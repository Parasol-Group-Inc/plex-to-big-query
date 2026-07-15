# Plex SQL Dev — Accounting Database: View Catalog

## Purpose

Financial data — Accounts Receivable, Accounts Payable, General Ledger, invoices,
and payments. AR invoices are generated from Sales Shippers (outbound shipments),
so there's a tight link back to `Sales.Shipper` and `Sales.Shipper_AR_Invoice`.

## Relevance to Sales Orders Pipeline

AR invoices are the billing records that result from fulfilled sales orders. Useful
for a revenue/billing dataset:
- `Sales.Shipper_AR_Invoice` links shipments → AR invoices
- `Accounting.AR_Invoice` has the actual dollar amounts, dates, payment status

---

## Estimated Views

### Accounts Receivable

| View | Status | Description |
|---|---|---|
| `AR_Invoice` ⭐ | ❓ | Customer invoice header — amount, date, due date, status |
| `AR_Invoice_Line` ⭐ | ❓ | Invoice line items — part, qty, price |
| `AR_Invoice_Status` | ❓ | Invoice status lookup |
| `AR_Invoice_Type` | ❓ | Invoice type (standard, credit memo, etc.) |
| `AR_Payment` | ❓ | Customer payment records |
| `AR_Payment_Method` | ❓ | Payment method lookup |
| `AR_Aging` | ❓ | Aging report data |
| `AR_Credit_Memo` | ❓ | Credit memos |
| `AR_Debit_Memo` | ❓ | Debit memos |
| `AR_Write_Off` | ❓ | Write-off records |

### Accounts Payable

| View | Status | Description |
|---|---|---|
| `AP_Invoice` | ❓ | Supplier invoice header |
| `AP_Invoice_Line` | ❓ | Supplier invoice line items |
| `AP_Invoice_Status` | ❓ | AP invoice status lookup |
| `AP_Payment` | ❓ | Supplier payment records |
| `AP_Payment_Method` | ❓ | Payment method lookup |

### General Ledger

| View | Status | Description |
|---|---|---|
| `GL_Account` | ❓ | Chart of accounts |
| `GL_Account_Type` | ❓ | Account type (Asset, Liability, Revenue, Expense) |
| `GL_Period` | ❓ | Accounting periods (fiscal calendar) |
| `GL_Transaction` | ❓ | Journal entries / GL postings |
| `GL_Budget` | ❓ | Budget amounts by account/period |

### Financial Setup

| View | Status | Description |
|---|---|---|
| `Cost_Center` | ❓ | Cost center / profit center master |
| `Tax_Code` | ❓ | Tax codes |
| `Tax_Rate` | ❓ | Tax rates by code |
| `Payment_Term` | ❓ | Payment terms (Net 30, etc.) |
| `Bank_Account` | ❓ | Company bank accounts |

### Period / Calendar

| View | Status | Description |
|---|---|---|
| `Fiscal_Year` | ❓ | Fiscal year setup |
| `Fiscal_Period` | ❓ | Fiscal period setup |
| `Accounting_Period` | ❓ | Open/closed accounting periods |

---

## How to Get the Full List

In Plex SQL Dev, expand: **Accounting → Views**, then paste the tree HTML here.

Suggested verification queries:
```sql
SELECT TOP 5 * FROM AR_Invoice
SELECT TOP 5 * FROM GL_Account
```
