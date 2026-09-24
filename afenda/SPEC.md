# AFENDA xForge v9 — product and engineering specification

AFENDA xForge is a self-hosted business-administration SaaS built on the Odoo
19.0 Community framework. It never depends on Odoo S.A. services at runtime.
This file says what the product must do and the rules the code follows; how to
run it is in [README.md](README.md). Upstream documentation is linked, not
repeated.

## 1. Scope and domains

| Domain | Built on (Community) | AFENDA scope |
|---|---|---|
| **Business Administration** | `res.company` (parent companies, branches), `res.partner`, `hr.department`, analytic plans, `stock.warehouse` | Group structure: legal entities, ownership, business units, cost centers, locations, shared business partners |
| Accounting / finance | `account`, `analytic`, `spreadsheet_account` | General ledger, invoicing, payments, taxes, period close, financial reporting |
| Sales / CRM / invoicing | `crm`, `sale_management`, `account` | Pipeline, quotations, orders, invoicing, customer portal |
| Inventory / MRP | `stock`, `purchase`, `mrp` | Warehouses, receipts and deliveries, BoMs, manufacturing orders |
| HR / payroll / projects | `hr`, `hr_holidays`, `hr_attendance`, `hr_expense`, `hr_timesheet`, `project` | Employees, leave, attendance, expenses, timesheets, projects |

**Carried over from v8** (`pohlai88/afenda-xForge-v8`, Next.js + Drizzle):

| v8 concept | v9 mapping |
|---|---|
| `tenant` (security boundary) | One PostgreSQL database per customer, `dbfilter = ^%d$` |
| `legal_entity` (statutory boundary, own currency and time zone) | `res.company`, with `parent_id` for group structure and branches |
| `consolidation_group` + member ownership % and method | Gap: `afenda_consolidation` (§8) |
| `business_unit`, `cost_center` | Analytic plans and accounts |
| `department`, `location` | `hr.department`, `stock.warehouse` / `stock.location` |
| `business_partner` (group-wide) + `partner_relationship` (per company) | Shared `res.partner` + company-dependent fields (receivable/payable accounts, payment terms, pricelists) |
| FIN-REV / FIN-CLS: posted journals immutable, reversal only, periods close in order | Journal hash lock + hard lock date (configuration, README §8) |
| Sensitive-data grants, encrypted MY identifiers (NRIC, passport, TIN) | Gap: `afenda_sensitive` (§8) |
| Payroll immutability PAY-001..011, Malaysian statutory (LHDN, KWSP, PERKESO) | Gap: OCA `payroll` + `afenda_l10n_my_payroll` (§8) |
| Workbench UX rules (AFENDA-UX-001..012) | §6 |

## 2. Requirements

**Functional** (each is met by upstream, OCA or an `afenda_*` module, per §8):

- **BA-1** An administrator can model a group of legal entities with parent/child ownership, each with its own currency, fiscal localization and time zone.
- **BA-2** A business partner is recorded once for the group and carries per-company terms.
- **BA-3** Users see only the companies they are granted; data never crosses tenants (separate databases).
- **FIN-1** Posted journal entries cannot be edited, reset to draft or deleted; corrections are reversals.
- **FIN-2** Periods close in order and a closed period cannot reopen (hard lock date).
- **FIN-3** Trial balance, general ledger, P&L, balance sheet and aged balances are available per company.
- **FIN-4** Bank statements can be imported and reconciled.
- **SAL-1** Leads flow to quotations, orders and invoices with no re-keying; customers see documents on the portal.
- **INV-1** Stock moves are double-entry and valued; manufacturing consumes components by BoM.
- **HR-1** Leave, attendance, expenses and timesheets are approved by managers and flow to accounting.
- **PLAT-1** No screen, email or document shows Odoo branding (tested).
- **PLAT-2** No runtime request reaches Odoo S.A. (§5).
- **PLAT-3** Each tenant exposes the JSON-2 API on its own subdomain, authenticated with per-user, expiring API keys; errors never carry server tracebacks or internal messages; administrators get the `/doc` explorer (README "API").

**Non-functional:**

| Area | Target |
|---|---|
| Capacity | about 6 concurrent users per worker; 4 vCPU / 8 GB box ≈ 45 concurrent users |
| Response | list and form views < 1 s p95 on the reference box |
| Availability | 99.5 % monthly; `/web/health` monitored |
| Backup | RPO ≤ 24 h (≤ 5 min with pgBackRest), RTO ≤ 2 h, weekly restore drill |
| Security | TLS only, 2FA available to every user, master password set, database manager off |
| Browsers | current Chrome, Edge, Firefox, Safari; PWA installable |
| Localization | Malaysia first (`l10n_my`); any Odoo localization usable |
| API | JSON-2 per tenant; rate-limited at nginx; covered end to end by `tests/test_api.py` |

## 3. Architecture and stack

**Layering rule:** upstream Odoo (never edited) → OCA modules (git
submodules, 19.0 branches) → `afenda/addons/afenda_*`. Every AFENDA change is
an `_inherit`, an XML `inherit_id`, an asset-bundle entry or data; if it cannot
be expressed that way, it goes upstream or into the roadmap, not into a patch.

| Layer | Technology | Version |
|---|---|---|
| Runtime | Python | 3.12 (3.10–3.14 supported) |
| Framework | Odoo Community: ORM, HTTP (Werkzeug), prefork workers, gevent websocket bus | 19.0 |
| Web client | OWL 2, QWeb, SCSS asset bundles | bundled |
| Database | PostgreSQL | 16 (14+) |
| Reports | wkhtmltopdf, patched Qt | 0.12.6.1 |
| Edge | nginx + certbot, systemd | distro |
| OCA | server-brand, web, server-tools | 19.0 |
| CI | GitHub Actions, ruff | — |

Upstream references: [ORM](https://www.odoo.com/documentation/19.0/developer/reference/backend/orm.html),
[security](https://www.odoo.com/documentation/19.0/developer/reference/backend/security.html),
[OWL framework](https://www.odoo.com/documentation/19.0/developer/reference/frontend/framework_overview.html),
[deployment](https://www.odoo.com/documentation/19.0/administration/on_premise/deploy.html).

## 4. AFENDA data conventions

- **Modules** are named `afenda_<domain>`; fields added by them are plain
  names on `_inherit` models (never `x_` studio-style fields).
- **Schema changes** ship with a manifest version bump and, when data must
  move, a `migrations/<version>/` script. Test the upgrade on a restored copy.
- **Money** uses `Monetary` fields and the currency's rounding; never float
  arithmetic on amounts outside the ORM helpers (`float_round`, `currency.round`).
- **Dates**: business dates are `Date` fields evaluated in the company's time
  zone; `Datetime` only for moments.
- **Ledger**: posted entries are hashed and immutable (README §8). An
  `afenda_*` module must never call `button_draft` on a posted move or write
  to hashed fields.
- **Deactivate, never delete** master data (`active` field); codes are unique
  per company.
- **Audit**: business models inherit `mail.thread` and track the fields that
  matter; OCA `auditlog` (in the server-tools submodule) for full field history.

## 5. Security and the self-hosted policy

Standard controls: `list_db = False`, strong `admin_passwd`, `auth_totp`
(2FA), `auth_passkey`, `auth_password_policy`, `limit_req` on login at nginx,
record rules and groups for every `afenda_*` model, backups encrypted at rest.

**No Odoo S.A. at runtime**, in four layers:

1. **Network** (the guarantee): the resolver sinks `odoo.com` and `odoocdn.com`;
   nginx sends `Content-Security-Policy: font-src 'self' data:` (README §3–4).
2. **Not installed**: OCA `module_change_auto_install` stops `iap`, `iap_mail`,
   `iap_crm`, `partner_autocomplete`, `snailmail`, `snailmail_account`, `sms`,
   `crm_sms`, `crm_iap_enrich`, `crm_iap_mine` from auto-installing
   (`odoo.conf`). An app that hard-depends on one still installs it
   (`point_of_sale` → `partner_autocomplete`, `base_automation` → `sms`).
3. **Endpoints**: `afenda_brand.hooks.block_odoo_services` points every
   overridable Odoo S.A. endpoint at a closed local port and keeps the VIES
   cron and "Odoo.com Accounts" login off, so features fail fast instead of
   hanging. It runs at install, in the 19.0.1.1.0 migration and at every
   start, so upgraded databases and apps installed later are covered. An
   administrator may point an endpoint at a real (non-Odoo) service; an empty
   one is reset.
4. **Guard**: `test_upstream_odoo_hosts_are_reviewed` fails when upstream code
   names an Odoo S.A. host that is not in its reviewed list.

| Service | Host | How it is cut |
|---|---|---|
| Publisher warranty (weekly usage report) | services.odoo.com | OCA `disable_odoo_online`, `publisher_warranty_url`, network |
| IAP credits, partner autocomplete, SMS, postal mail, lead enrichment/mining, website reveal | iap*.odoo.com, partner-autocomplete, sms.api, iap-snailmail | Not installed (2) + endpoint (3) + network |
| Editor media library and AI text | media-api, olg.api | Endpoint (3) + network |
| Website builder APIs | website.api, olg.api | Endpoint (3) + network |
| VIES VAT validation | vies.api.odoo.com | Called only if a company enables *Verify VAT Numbers* (off by default). Cron off (3) + network; use the EU VIES service directly if needed |
| "Sign in with Odoo.com" | accounts.odoo.com | Provider off (3); use OCA `auth_oidc` for SSO |
| Apps store, "Industries" filter | apps.odoo.com | OCA `disable_odoo_online` hides the menus; network |
| Noto fonts for non-Latin scripts | fonts.odoocdn.com | CSP (1). The AFENDA font stacks deliberately skip Odoo's `o-add-unicode-support-font()` wrapper, so the web client falls back to system fonts for Cyrillic, Hebrew, Arabic and Telugu; self-host Noto if those scripts matter |
| Digest and mailing images | download.odoocdn.com | Loaded by the recipient's mail client; turn off digest tips or edit templates |
| Gmail / Outlook OAuth proxy | gmail.api, outlook.api | Community refuses it; configure your own OAuth client |
| Payment onboarding | stripe/razorpay/payu/mercadopago.api | Enter API keys manually |
| E-invoicing proxies (Peppol, IT, IN, GR, DK, FR, **MY MyInvois**) | *-edi.api, peppol.api, pdp.api | Do not register; **MyInvois needs a direct LHDN integration** (§8) |
| IoT box | iot-proxy.odoo.com | Not used server-side |

## 6. UI/UX rules

- **Tokens** come from `afenda_brand/brand.py` (mirrored in `primary_variables.scss`); never hard-code a brand hex in another module, use `$o-brand-primary`.
- **One primary action per screen**, in Ledger Blue; everything else secondary.
- **Numbers read as data**: tabular figures on money, quantities and references; right-aligned in lists.
- **Status colours mean one thing**: verified = posted/reconciled, ember = needs attention/overdue, flag = error/locked.
- **Financial truth waits for the server**: no optimistic totals on posted documents.
- **Keyboard first**: every AFENDA view works with Odoo's hotkeys; no mouse-only actions.
- **Accessibility**: WCAG 2.1 AA contrast (Ledger Blue on white and paper passes); visible focus.
- **No Odoo tells**: branding tests cover login, web client, PWA, emails, bot.

## 7. Definition of Done

A change is done when:

1. `.github/workflows/afenda.yml` is green: `ruff check afenda/addons`, then a
   fresh database installs `afenda_brand` and every changed `afenda_*` module
   with their tests passing and no ERROR in the log.
2. New behaviour has a test; a bug fix has a test that failed before it.
3. Schema changes were upgraded (`-u`) on a restored copy of production data.
4. `odoo/` and `addons/` are untouched (`git diff --stat` shows none).
5. README (operations) or this spec (behaviour) is updated in the same change.
6. One reviewer approved.

## 8. Community vs Enterprise: gaps and roadmap

Enterprise features Community omits, and how AFENDA covers them. **OCA 19.0**
= module present on the OCA 19.0 branch (checked 2026-09-24).

| Enterprise | What it does | AFENDA path | OCA 19.0 |
|---|---|---|---|
| **Accounting** | | | |
| `account_accountant` / `account_reports` | Interactive P&L, balance sheet, GL, aged balances, tax report | `account_financial_report`, `mis_builder` | yes |
| Bank reconciliation widget | Match statement lines to entries | `account_reconcile_oca` | yes |
| `account_asset` | Fixed assets and depreciation | `account_asset_management` | yes |
| `account_followup` | Payment reminders | `account_credit_control` | yes |
| `account_budget` | Budgets vs actuals | `account_budget_oca` | yes |
| `currency_rate_live` | Daily exchange rates | `currency_rate_update` (add a Bank Negara Malaysia provider) | yes |
| `account_batch_payment`, SEPA | Payment runs | `account_payment_order`, `account_banking_sepa_*` | yes |
| `account_bank_statement_import_*` | CAMT/OFX/CSV import | `account_statement_import_*` | yes |
| `account_consolidation` | Group consolidation | **build `afenda_consolidation`** (ownership %, method, eliminations; from v8) | — |
| `account_invoice_extract` | OCR of bills | later; self-hosted OCR, never Odoo IAP | — |
| **Sales** | | | |
| `sale_subscription` | Recurring billing | `contract`, `subscription_oca` | yes |
| `sale_commission` | Commissions | `sale_commission_oca` (OCA/commission) | yes |
| `sale_renting` | Rentals | later | — |
| **Inventory / MRP** | | | |
| `stock_barcode` | Barcode scanning app | `stock_barcodes` | no (16.0 last) |
| `mrp_mps` | Master production schedule | `mrp_multi_level` | yes |
| `quality_control` | Quality checks | `quality_control_oca` | yes |
| `mrp_plm` | Engineering changes | later | — |
| `mrp_workorder` shop floor | Tablet UI for operators | later | — |
| **HR / services** | | | |
| `hr_payroll` | Payslips, statutory | OCA `payroll` + **build `afenda_l10n_my_payroll`** (LHDN, KWSP, PERKESO; v8 PAY rules) | yes |
| `timesheet_grid` | Timesheet grid and validation | `hr_timesheet_sheet` | no (18.0) |
| `helpdesk` | Tickets | `helpdesk_mgmt` | yes |
| `industry_fsm` | Field service | `fieldservice` | yes |
| `planning`, `hr_appraisal` | Shift planning, reviews | later | — |
| **Platform** | | | |
| `web_gantt` | Gantt view | `web_timeline` (already in the OCA/web submodule) | yes |
| `documents` | Document management | `dms` | yes |
| `sign` | E-signature | `sign_oca` | yes |
| `knowledge` | Wiki | `document_page` | yes |
| `approvals` | Multi-tier approvals | `base_tier_validation` | no (18.0) |
| `web_studio` | No-code customization | none; customize in `afenda_*` code | — |
| `spreadsheet_edition` | Editable spreadsheets | Community dashboards are read-only; later | — |
| **Malaysia** | | | |
| `l10n_my_edi` via Odoo proxy | MyInvois e-invoicing | **build `afenda_l10n_my_myinvois`**, direct to LHDN (reuse `amaseng/myinvois-open-sdk`, Apache-2.0) | none exists |

**Where AFENDA improves on Enterprise** (candidate `afenda_*` work, in order):

1. **Ledger integrity in the UI**: show hash status and lock dates on every
   journal and entry; refuse, not just hide, anything that would un-post.
2. **Period close checklist**: bank reconciled, drafts posted, reports
   reviewed, then hard lock — one screen per company per period.
3. **MyInvois direct**: no middleman, submission status on the invoice.
4. **Group view**: consolidation groups with ownership and elimination rules.
5. **Sensitive data**: field-level grants and encryption for personal identifiers.

Adopting a module: add the OCA repository as a submodule on 19.0, add it to
`addons_path` in both configurations, depend on it from an `afenda_*` module,
and test it like our own.

## 9. Decisions

- **D1 Self-hosted, no Odoo S.A.** The product must run with no contract or
  connection to Odoo S.A.; enforced in four layers (§5).
- **D2 Never edit upstream.** Forks that diverged (Flectra from Odoo 11) paid
  for every upstream merge. AFENDA changes are add-ons; tracking OCA/OCB 19.0
  instead of odoo/odoo stays an option.
- **D3 OCA first.** Adopt a maintained OCA module before writing one; write
  `afenda_*` only for gaps and AFENDA-specific rules.
- **D4 Native VPS.** systemd + nginx on one host until load needs more;
  Docker (Tecnativa doodba) is the path when it does.
- **D5 Immutable ledger by configuration.** Odoo's hash lock and hard lock
  date already enforce v8's rules; code only for what they miss.
- **D6 One database per tenant.** Strongest isolation, simplest backup and
  restore per customer, native to Odoo (`dbfilter`).
- **D7 Upstream-compatible API contract.** Error `name`s (`odoo.exceptions.*`)
  and the `X-Odoo-Database` header keep their upstream names so existing Odoo
  client libraries work; only tracebacks and internal 500 messages are removed.
