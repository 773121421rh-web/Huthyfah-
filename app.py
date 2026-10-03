CREATE TABLE IF NOT EXISTS roles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    full_name TEXT NOT NULL,
    role_code TEXT NOT NULL,
    is_active INTEGER DEFAULT 1,
    created_at TEXT DEFAULT (datetime('now','localtime'))
);

CREATE TABLE IF NOT EXISTS company_info (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    name TEXT, commercial_reg TEXT, tax_number TEXT, address TEXT, phone TEXT, email TEXT, currency_code TEXT DEFAULT 'YER', vat_rate REAL DEFAULT 15
);

CREATE TABLE IF NOT EXISTS currencies (
    code TEXT PRIMARY KEY,
    name TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS exchange_rates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    currency_code TEXT NOT NULL,
    rate REAL NOT NULL,  -- rate against base currency YER
    rate_date TEXT NOT NULL,
    created_at ...
);

CREATE TABLE IF NOT EXISTS cost_centers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    branch TEXT,
    is_active INTEGER DEFAULT 1
);

CREATE TABLE IF NOT EXISTS accounts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    type TEXT NOT NULL CHECK (type IN ('asset','liability','equity','revenue','expense')),
    parent_code TEXT,
    is_group INTEGER DEFAULT 0,
    is_active INTEGER DEFAULT 1
);

CREATE TABLE IF NOT EXISTS warehouses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    location TEXT
);

CREATE TABLE IF NOT EXISTS products (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sku TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    category TEXT,
    unit TEXT DEFAULT 'قطعة',
    cost_price REAL DEFAULT 0,
    sale_price REAL DEFAULT 0,
    reorder_level REAL DEFAULT 10,
    warehouse_id INTEGER,
    quantity REAL DEFAULT 0,  -- current stock
    is_active INTEGER DEFAULT 1,
    created_at ...
);

CREATE TABLE IF NOT EXISTS stock_movements (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id INTEGER NOT NULL,
    movement_type TEXT NOT NULL CHECK (movement_type IN ('in','out','adjust')),
    quantity REAL NOT NULL,
    unit_cost REAL DEFAULT 0,
    reference TEXT,
    notes TEXT,
    moved_at TEXT DEFAULT ...
);

CREATE TABLE IF NOT EXISTS stock_counts ( -- جرد
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    warehouse_id ...,
    count_date TEXT,
    status TEXT DEFAULT 'draft', -- draft, approved
    notes
);

CREATE TABLE IF NOT EXISTS stock_count_lines (...);

CREATE TABLE IF NOT EXISTS contacts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT UNIQUE,
    name TEXT NOT NULL,
    contact_type TEXT NOT NULL CHECK (contact_type IN ('customer','supplier','both')),
    phone, email, address, tax_number,
    balance REAL DEFAULT 0, -- optional
    is_active ...
);

CREATE TABLE IF NOT EXISTS invoices (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    invoice_no TEXT UNIQUE NOT NULL,
    invoice_type TEXT NOT NULL CHECK (invoice_type IN ('sales','purchase')),
    contact_id INTEGER NOT NULL,
    invoice_date TEXT NOT NULL,
    subtotal REAL DEFAULT 0,
    discount REAL DEFAULT 0,
    tax REAL DEFAULT 0,
    total REAL DEFAULT 0,
    paid REAL DEFAULT 0,
    payment_method TEXT, -- cash, credit
    journal_id INTEGER, -- link to journal entry
    created_by TEXT,
    created_at ...
);

CREATE TABLE IF NOT EXISTS invoice_lines (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    invoice_id INTEGER NOT NULL,
    product_id INTEGER NOT NULL,
    quantity REAL NOT NULL,
    unit_price REAL NOT NULL,
    line_total REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS employees (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    emp_no TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    department TEXT,
    job_title TEXT,
    hire_date TEXT,
    basic_salary REAL DEFAULT 0,
    allowances REAL DEFAULT 0,
    phone, national_id, status TEXT DEFAULT 'active',
    bank_account
);

CREATE TABLE IF NOT EXISTS attendance (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    employee_id INTEGER NOT NULL,
    att_date TEXT NOT NULL,
    check_in TEXT,
    check_out TEXT,
    status TEXT DEFAULT 'present', -- present, absent, leave, sick, holiday
    notes,
    UNIQUE(employee_id, att_date)
);

CREATE TABLE IF NOT EXISTS payroll_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    period TEXT NOT NULL, -- 2025-01
    run_date TEXT,
    total_gross REAL,
    total_deductions REAL,
    total_net REAL,
    journal_id INTEGER,
    created_by,
    UNIQUE(period)
);

CREATE TABLE IF NOT EXISTS payroll_lines (
    id ...,
    payroll_id ...,
    employee_id ...,
    basic REAL, allowances REAL, deductions REAL, net REAL
);

CREATE TABLE IF NOT EXISTS expenses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    expense_date TEXT,
    category TEXT, -- rent, utilities, other
    amount REAL,
    description TEXT,
    paid_from TEXT, -- account code (cash/bank)
    cost_center_id INTEGER,
    journal_id INTEGER,
    created_by,
    created_at
);

CREATE TABLE IF NOT EXISTS journal_entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    entry_no TEXT UNIQUE NOT NULL,
    entry_date TEXT NOT NULL,
    description TEXT,
    source TEXT DEFAULT 'manual', -- manual, sales, purchase, payroll, expense
    source_id INTEGER,
    cost_center_id INTEGER,
    created_by TEXT,
    created_at ...
);

CREATE TABLE IF NOT EXISTS journal_lines (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    entry_id INTEGER NOT NULL,
    account_code TEXT NOT NULL,
    account_name TEXT,
    debit REAL DEFAULT 0,
    credit REAL DEFAULT 0,
    cost_center_id INTEGER,
    line_desc TEXT
);
