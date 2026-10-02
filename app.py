"""
SUPER ERP SYSTEM - ENTERPRISE EDITION (V5)
نظام مؤسسي شامل ومتوسع للمبيعات، المشتريات، المخازن، الموارد البشرية، والحسابات.
"""
import sqlite3, hashlib, os
from datetime import datetime, date
from contextlib import contextmanager
import pandas as pd
import streamlit as st

# ==========================================
# 0. إعدادات الصفحة وتصميم واجهات المستخدم
# ==========================================
st.set_page_config(page_title="SUPER ERP ENTERPRISE", page_icon="🏛️", layout="wide", initial_sidebar_state="expanded")

st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Tajawal:wght@400;500;700&display=swap');
    html, body, [class*="css"] {
        font-family: 'Tajawal', sans-serif !important;
    }
    .stButton>button {
        border-radius: 8px;
        transition: all 0.3s;
        font-weight: bold;
    }
    .stButton>button:hover {
        transform: translateY(-2px);
        box-shadow: 0 4px 10px rgba(0,0,0,0.15);
    }
    .main-header {
        color: #1f77b4;
        border-bottom: 2px solid #f0f2f6;
        padding-bottom: 8px;
        margin-bottom: 20px;
    }
    </style>
""", unsafe_allow_html=True)

# ==========================================
# 1. إعدادات قاعدة البيانات وهيكلتها (V5)
# ==========================================
DB_FILE = os.getenv("ERP_DB", "super_erp_v5.db")
ROLES = ["مدير النظام", "محاسب", "موظف مبيعات", "مدير مشتريات", "مدير موارد بشرية"]
BASE_CURRENCY = "YER"

def now(): return datetime.now().isoformat(timespec="seconds")
def money(v): return f"{float(v or 0):,.2f}"
def next_no(prefix): return f"{prefix}-{datetime.now().strftime('%y%m%d%H%M%S')}"
def hash_password(password): return hashlib.sha256(password.encode("utf-8")).hexdigest()

@contextmanager
def get_db():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

def q(sql, params=(), many=False):
    with get_db() as conn:
        cur = conn.cursor()
        if many: cur.executemany(sql, params)
        else: cur.execute(sql, params)
        return cur.fetchall()

def get_df(sql, params=()):
    rows = q(sql, params)
    return pd.DataFrame([dict(r) for r in rows]) if rows else pd.DataFrame()

def init_db():
    with get_db() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS company_info(
            id INTEGER PRIMARY KEY, name TEXT, tax_no TEXT, address TEXT, phone TEXT);
        CREATE TABLE IF NOT EXISTS users(
            id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL, full_name TEXT, role TEXT NOT NULL, active INTEGER DEFAULT 1);
        CREATE TABLE IF NOT EXISTS currencies(
            code TEXT PRIMARY KEY, name TEXT, exchange_rate REAL);
        CREATE TABLE IF NOT EXISTS cost_centers(
            id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE, active INTEGER DEFAULT 1);
        CREATE TABLE IF NOT EXISTS products(
            id INTEGER PRIMARY KEY AUTOINCREMENT, sku TEXT UNIQUE, name TEXT, 
            cost_price REAL, sale_price REAL, stock_qty REAL, active INTEGER DEFAULT 1);
        CREATE TABLE IF NOT EXISTS contacts(
            id INTEGER PRIMARY KEY AUTOINCREMENT, kind TEXT, name TEXT, phone TEXT, address TEXT);
        CREATE TABLE IF NOT EXISTS invoices(
            id INTEGER PRIMARY KEY AUTOINCREMENT, invoice_no TEXT UNIQUE, invoice_type TEXT, 
            contact_name TEXT, total REAL, paid REAL, status TEXT, created_at TEXT, user_id INTEGER);
        CREATE TABLE IF NOT EXISTS employees(
            id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, department TEXT, job_title TEXT, basic_salary REAL, active INTEGER DEFAULT 1);
        CREATE TABLE IF NOT EXISTS attendance(
            id INTEGER PRIMARY KEY AUTOINCREMENT, employee_id INTEGER, work_date TEXT, status TEXT, notes TEXT,
            UNIQUE(employee_id, work_date));
        CREATE TABLE IF NOT EXISTS accounts(
            code TEXT PRIMARY KEY, name TEXT, account_type TEXT);
        CREATE TABLE IF NOT EXISTS journal_entries(
            id INTEGER PRIMARY KEY AUTOINCREMENT, entry_no TEXT UNIQUE, date TEXT, description TEXT, user_id INTEGER);
        CREATE TABLE IF NOT EXISTS journal_lines(
            id INTEGER PRIMARY KEY AUTOINCREMENT, entry_id INTEGER, account_code TEXT, cost_center_id INTEGER,
            debit REAL DEFAULT 0, credit REAL DEFAULT 0, currency_code TEXT, exchange_rate REAL);
        """)
        
        # البيانات الافتراضية
        if c.execute("SELECT COUNT(*) FROM company_info").fetchone()[0] == 0:
            c.execute("INSERT INTO company_info (id, name, tax_no) VALUES (1, 'مؤسسة يمن سوفت التجارية', '100200300')")
        
        admin_check = c.execute("SELECT COUNT(*) FROM users WHERE username='admin'").fetchone()[0]
        if admin_check == 0:
            c.execute("INSERT INTO users(username, password_hash, full_name, role, active) VALUES(?,?,?,?,?)",
                      ("admin", hash_password("admin"), "المدير العام", "مدير النظام", 1))

        if c.execute("SELECT COUNT(*) FROM currencies").fetchone()[0] == 0:
            c.executemany("INSERT INTO currencies VALUES(?,?,?)", [("YER", "ريال يمني", 1.0), ("USD", "دولار أمريكي", 530.0), ("SAR", "ريال سعودي", 140.0)])
        if c.execute("SELECT COUNT(*) FROM cost_centers").fetchone()[0] == 0:
            c.executemany("INSERT INTO cost_centers(name) VALUES(?)", [("المركز الرئيسي - صنعاء",), ("فرع عدن",)])
        if c.execute("SELECT COUNT(*) FROM accounts").fetchone()[0] == 0:
            accounts = [("101","الصندوق الرئيسي","أصول"),("102","البنك","أصول"),("103","المخزون","أصول"),
                        ("104","العملاء (ذمم)","أصول"),("201","الموردون (ذمم)","خصوم"),("301","رأس المال","حقوق ملكية"),
                        ("401","إيرادات المبيعات","إيرادات"),("501","تكلفة المبيعات","مصروفات"),
                        ("502","مصروفات الرواتب والأجور","مصروفات"),("503","مصروفات تشغيلية متنوعة","مصروفات")]
            c.executemany("INSERT INTO accounts VALUES(?,?,?)", accounts)

# ==========================================
# 2. نظام التحقق والصلاحيات (RBAC)
# ==========================================
def require_role(allowed_roles):
    if st.session_state.role not in allowed_roles:
        st.error(f"🔒 عذراً {st.session_state.full_name}، صلاحية '{st.session_state.role}' لا تمنحك حق الوصول لهذه الشاشة.")
        st.stop()

def post_journal(desc, lines):
    debit = round(sum(float(x.get("debit", 0)) for x in lines), 2)
    credit = round(sum(float(x.get("credit", 0)) for x in lines), 2)
    if debit != credit: return False, f"القيد غير متزن (الفرق المحاسبي: {debit - credit})"
    
    entry_no = next_no("JE")
    with get_db() as c:
        eid = c.execute("INSERT INTO journal_entries(entry_no, date, description, user_id) VALUES(?,?,?,?)",
                        (entry_no, date.today().isoformat(), desc, st.session_state.user_id)).lastrowid
        for x in lines:
            c.execute("INSERT INTO journal_lines(entry_id, account_code, cost_center_id, debit, credit, currency_code, exchange_rate) VALUES(?,?,?,?,?,?,?)",
                      (eid, x["acc"], x.get("cc_id"), x.get("debit",0), x.get("credit",0), x.get("currency","YER"), x.get("rate",1)))
    return True, entry_no

# ==========================================
# 3. واجهة تسجيل الدخول
# ==========================================
init_db()
if "logged_in" not in st.session_state: st.session_state.logged_in = False

if not st.session_state.logged_in:
    col1, col2, col3 = st.columns([1,2,1])
    with col2:
        st.markdown("<h1 style='text-align: center; color: #1f77b4;'>🏛️ SUPER ERP ENTERPRISE</h1>", unsafe_allow_html=True)
        st.markdown("<p style='text-align: center;'>بوابة الدخول الموحدة للمؤسسة</p>", unsafe_allow_html=True)
        st.info("💡 اسم المستخدم: **admin** | كلمة المرور: **admin**")
        
        with st.form("login_form"):
            username = st.text_input("👤 اسم المستخدم", value="admin")
            password = st.text_input("🔑 كلمة المرور", type="password", value="admin")
            submit = st.form_submit_button("تسجيل الدخول 🚀", use_container_width=True)
            
        if submit:
            user_data = q("SELECT * FROM users WHERE username=? AND active=1", (username,))
            if user_data and user_data[0]["password_hash"] == hash_password(password):
                st.session_state.update(logged_in=True, user_id=user_data[0]["id"], username=username, 
                                        full_name=user_data[0]["full_name"], role=user_data[0]["role"])
                st.rerun()
            else: 
                st.error("❌ بيانات الدخول غير صحيحة.")
    st.stop()

# ==========================================
# 4. القائمة الجانبية الموحدة (Navigation)
# ==========================================
comp_info = q("SELECT * FROM company_info WHERE id=1")[0]
st.sidebar.markdown(f"<h3 style='text-align:center;'>{comp_info['name']}</h3>", unsafe_allow_html=True)
st.sidebar.markdown(f"<p style='text-align:center; color:gray;'>المستخدم: {st.session_state.full_name}<br>({st.session_state.role})</p>", unsafe_allow_html=True)
st.sidebar.divider()

menu = [
    "📊 لوحة المؤشرات", 
    "🛒 المبيعات ونقاط البيع", 
    "📦 المشتريات والموردون", 
    "📦 إدارة المخازن والأصناف", 
    "👥 الموارد البشرية والرواتب", 
    "📅 الحضور والغياب", 
    "💰 الحسابات والقيود اليومية", 
    "📄 التقارير المالية الختامية", 
    "⚙️ إعدادات النظام والصلاحيات"
]
choice = st.sidebar.radio("اختر القسم:", menu)

if st.sidebar.button("🚪 تسجيل الخروج", use_container_width=True):
    st.session_state.clear()
    st.rerun()

# ==========================================
# 5. الوحدات البرمجية الكاملة للنظام
# ==========================================

# --- 1. لوحة المؤشرات ---
if choice == "📊 لوحة المؤشرات":
    st.markdown("<h2 class='main-header'>لوحة المؤشرات التنفيذية الشاملة</h2>", unsafe_allow_html=True)
    
    col1, col2, col3, col4 = st.columns(4)
    sales = get_df("SELECT SUM(total) as t FROM invoices WHERE invoice_type='بيع'")['t'].sum() or 0
    prods = get_df("SELECT COUNT(*) as c FROM products")['c'].sum() or 0
    emps = get_df("SELECT COUNT(*) as c FROM employees WHERE active=1")['c'].sum() or 0
    custs = get_df("SELECT COUNT(*) as c FROM contacts WHERE kind='عميل'")['c'].sum() or 0
    
    col1.metric("إجمالي المبيعات", f"{money(sales)} {BASE_CURRENCY}")
    col2.metric("أصناف المخزن", int(prods))
    col3.metric("إجمالي الموظفين", int(emps))
    col4.metric("قاعدة العملاء", int(custs))
    
    st.divider()
    left, right = st.columns(2)
    with left:
        st.subheader("آخر الفواتير المسجلة")
        st.dataframe(get_df("SELECT invoice_no AS الرقم, invoice_type AS النوع, contact_name AS الجهة, total AS الإجمالي, created_at AS التاريخ FROM invoices ORDER BY id DESC LIMIT 5"), use_container_width=True, hide_index=True)
    with right:
        st.subheader("حركات القيود اليومية الأخيرة")
        st.dataframe(get_df("SELECT entry_no AS القيد, date AS التاريخ, description AS البيان FROM journal_entries ORDER BY id DESC LIMIT 5"), use_container_width=True, hide_index=True)

# --- 2. المبيعات ونقاط البيع ---
elif choice == "🛒 المبيعات ونقاط البيع":
    require_role(["مدير النظام", "موظف مبيعات", "محاسب"])
    st.markdown("<h2 class='main-header'>شاشة المبيعات وإصدار الفواتير</h2>", unsafe_allow_html=True)
    
    products = get_df("SELECT id, sku, name, sale_price, cost_price, stock_qty FROM products WHERE active=1")
    customers = get_df("SELECT name FROM contacts WHERE kind='عميل'")
    
    if products.empty:
        st.warning("الرجاء إضافة أصناف في المخزن أولاً.")
    else:
        with st.form("pos_form"):
            c1, c2 = st.columns(2)
            cust_list = customers['name'].tolist() if not customers.empty else ["عميل نقدي عام"]
            cust_name = c1.selectbox("العميل:", cust_list)
            
            prod_dict = {f"{r['sku']} - {r['name']} (متوفر: {r['stock_qty']})": r for _, r in products.iterrows()}
            selected_prod = c2.selectbox("اختر الصنف:", list(prod_dict.keys()))
            
            c3, c4 = st.columns(2)
            qty = c3.number_input("الكمية:", min_value=1, value=1)
            payment_status = c4.selectbox("حالة الدفع:", ["مكتملة (نقداً)", "آجل (ذمم مدينة)"])
            
            if st.form_submit_button("إصدار وتدوير الفاتورة محاسبياً 🧾", type="primary"):
                p = prod_dict[selected_prod]
                if qty > p['stock_qty']:
                    st.error("الكمية المطلوبة تتجاوز رصيد المخزن الحالي!")
                else:
                    t_sale = qty * p['sale_price']
                    t_cost = qty * p['cost_price']
                    inv_no = next_no("SAL")
                    
                    with get_db() as conn:
                        conn.execute("UPDATE products SET stock_qty = stock_qty - ? WHERE id=?", (qty, p['id']))
                        conn.execute("INSERT INTO invoices(invoice_no, invoice_type, contact_name, total, paid, status, created_at, user_id) VALUES(?,?,?,?,?,?,?,?)",
                                     (inv_no, "بيع", cust_name, t_sale, t_sale if "نقداً" in payment_status else 0, payment_status, now(), st.session_state.user_id))
                    
                    lines = [
                        {"acc": "101" if "نقداً" in payment_status else "104", "debit": t_sale},
                        {"acc": "401", "credit": t_sale},
                        {"acc": "501", "debit": t_cost},
                        {"acc": "103", "credit": t_cost}
                    ]
                    post_journal(f"فاتورة مبيعات رقم {inv_no} للعميل {cust_name}", lines)
                    st.success(f"تم إصدار الفاتورة بنجاح برقم {inv_no} بقيمة {money(t_sale)}")
                    st.rerun()

# --- 3. المشتريات والموردون ---
elif choice == "📦 المشتريات والموردون":
    require_role(["مدير النظام", "مدير مشتريات", "محاسب"])
    st.markdown("<h2 class='main-header'>إدارة المشتريات وحسابات الموردين</h2>", unsafe_allow_html=True)
    
    t1, t2 = st.tabs(["إثبات فاتورة مشتريات", "إدارة جهات الاتصال (عملاء / موردون)"])
    
    with t1:
        products = get_df("SELECT id, sku, name, cost_price FROM products WHERE active=1")
        suppliers = get_df("SELECT name FROM contacts WHERE kind='مورد'")
        
        with st.form("pur_form"):
            c1, c2 = st.columns(2)
            sup_list = suppliers['name'].tolist() if not suppliers.empty else ["مورد عام"]
            sup_name = c1.selectbox("المورد:", sup_list)
            
            p_dict = {f"{r['sku']} - {r['name']}": r for _, r in products.iterrows()}
            selected_p = c2.selectbox("اختر الصنف الوارد:", list(p_dict.keys()))
            
            c3, c4 = st.columns(2)
            p_qty = c3.number_input("الكمية المشتراة:", min_value=1, value=1)
            p_cost = c4.number_input("تكلفة الشراء للوحدة:", min_value=0.0, value=float(p_dict[selected_p]['cost_price']) if p_dict else 0.0)
            
            if st.form_submit_button("إثبات الشراء وتحديث المخزن"):
                p = p_dict[selected_p]
                total_cost = p_qty * p_cost
                inv_no = next_no("PUR")
                
                with get_db() as conn:
                    conn.execute("UPDATE products SET stock_qty = stock_qty + ?, cost_price = ? WHERE id=?", (p_qty, p_cost, p['id']))
                    conn.execute("INSERT INTO invoices(invoice_no, invoice_type, contact_name, total, paid, status, created_at, user_id) VALUES(?,?,?,?,?,?,?,?)",
                                 (inv_no, "شراء", sup_name, total_cost, total_cost, "مكتملة", now(), st.session_state.user_id))
                
                lines = [
                    {"acc": "103", "debit": total_cost},
                    {"acc": "101", "credit": total_cost}
                ]
                post_journal(f"فاتورة مشتريات رقم {inv_no} من المورد {sup_name}", lines)
                st.success("تم تسجيل المشتريات وإضافة البضاعة للمخزن وتوليد القيد المحاسبي.")
                st.rerun()
                
    with t2:
        with st.form("contact_form"):
            c1, c2, c3 = st.columns(3)
            kind = c1.selectbox("نوع الجهة:", ["عميل", "مورد"])
            c_name = c2.text_input("اسم الجهة / الشركة")
            c_phone = c3.text_input("رقم الهاتف")
            if st.form_submit_button("حفظ الجهة"):
                if c_name:
                    q("INSERT INTO contacts(kind, name, phone) VALUES(?,?,?)", (kind, c_name, c_phone))
                    st.success("تم الحفظ بنجاح.")
                    st.rerun()
                else: st.error("اسم الجهة مطلوب.")
        st.dataframe(get_df("SELECT kind AS التصنيف, name AS الاسم, phone AS الهاتف FROM contacts"), use_container_width=True, hide_index=True)

# --- 4. إدارة المخازن والأصناف ---
elif choice == "📦 إدارة المخازن والأصناف":
    require_role(["مدير النظام", "محاسب", "مدير مشتريات"])
    st.markdown("<h2 class='main-header'>إدارة الأصناف والمخزون</h2>", unsafe_allow_html=True)
    
    with st.form("product_reg"):
        c1, c2 = st.columns(2)
        sku = c1.text_input("رمز الصنف (SKU)")
        name = c2.text_input("اسم الصنف")
        c3, c4, c5 = st.columns(3)
        cost = c3.number_input("تكلفة الشراء", min_value=0.0)
        sale = c4.number_input("سعر البيع", min_value=0.0)
        opening = c5.number_input("الرصيد الافتتاحي", min_value=0.0)
        
        if st.form_submit_button("تسجيل صنف جديد"):
            if sku and name:
                try:
                    q("INSERT INTO products(sku, name, cost_price, sale_price, stock_qty) VALUES(?,?,?,?,?)",
                      (sku, name, cost, sale, opening))
                    st.success("تم تسجيل الصنف.")
                    st.rerun()
                except sqlite3.IntegrityError: st.error("رمز الصنف مسجل مسبقاً!")
            else: st.error("الرمز والاسم مطلوبان.")
            
    st.subheader("جرد المخزون اللحظي")
    st.dataframe(get_df("SELECT sku AS الرمز, name AS الصنف, cost_price AS التكلفة, sale_price AS سعر_البيع, stock_qty AS الرصيد_المتوفر FROM products"), use_container_width=True, hide_index=True)

# --- 5. الموارد البشرية والرواتب ---
elif choice == "👥 الموارد البشرية والرواتب":
    require_role(["مدير النظام", "مدير موارد بشرية"])
    st.markdown("<h2 class='main-header'>شؤون الموظفين ومسير الرواتب</h2>", unsafe_allow_html=True)
    
    t1, t2 = st.tabs(["إضافة موظف", "مسير الرواتب الشهري"])
    
    with t1:
        with st.form("emp_form"):
            c1, c2 = st.columns(2)
            e_name = c1.text_input("اسم الموظف الكامل")
            e_dept = c2.selectbox("القسم الإداري", ["الإدارة العليا", "المبيعات", "المشتريات", "المحاسبة", "المخازن"])
            c3, c4 = st.columns(2)
            e_job = c3.text_input("المسمى الوظيفي")
            e_sal = c4.number_input("الراتب الأساسي", min_value=0.0, step=1000.0)
            
            if st.form_submit_button("اعتماد الموظف"):
                if e_name:
                    q("INSERT INTO employees(name, department, job_title, basic_salary) VALUES(?,?,?,?)",
                      (e_name, e_dept, e_job, e_sal))
                    st.success("تم حفظ بيانات الموظف.")
                    st.rerun()
                else: st.error("اسم الموظف مطلوب.")
        st.dataframe(get_df("SELECT name AS الموظف, department AS القسم, job_title AS المسمى, basic_salary AS الراتب FROM employees WHERE active=1"), use_container_width=True, hide_index=True)
        
    with t2:
        st.subheader("صرف الرواتب الشامل")
        total_sal = get_df("SELECT SUM(basic_salary) as s FROM employees WHERE active=1")['s'].sum() or 0
        st.metric("إجمالي مسير الرواتب المستحق", f"{money(total_sal)} {BASE_CURRENCY}")
        
        if st.button("ترحيل مسير الرواتب وصرفها من البنك 💸", type="primary"):
            if total_sal > 0:
                lines = [
                    {"acc": "502", "debit": total_sal},
                    {"acc": "102", "credit": total_sal}
                ]
                post_journal("صرف مسير الرواتب والأجور الشهري للموظفين", lines)
                st.success("تم صرف الرواتب وتوليد القيد المحاسبي المزدوج بنجاح.")
            else: st.warning("لا توجد رواتب مسجلة للصرف.")

# --- 6. الحضور والغياب ---
elif choice == "📅 الحضور والغياب":
    require_role(["مدير النظام", "مدير موارد بشرية"])
    st.markdown("<h2 class='main-header'>متابعة الحضور والغياب اليومي</h2>", unsafe_allow_html=True)
    
    emps = q("SELECT id, name FROM employees WHERE active=1")
    if not emps:
        st.warning("لا يوجد موظفون مسجلون.")
    else:
        with st.form("att_form"):
            emp_dict = {r['name']: r['id'] for r in emps}
            sel_emp = st.selectbox("الموظف:", list(emp_dict.keys()))
            att_date = st.date_input("تاريخ اليوم:", date.today())
            status = st.selectbox("الحالة:", ["حاضر", "غائب", "إجازة رسمية", "مهمة عمل"])
            notes = st.text_input("ملاحظات إضافية")
            
            if st.form_submit_button("تسجيل وحفظ الحضور"):
                emp_id = emp_dict[sel_emp]
                try:
                    q("INSERT INTO attendance(employee_id, work_date, status, notes) VALUES(?,?,?,?)",
                      (emp_id, str(att_date), status, notes))
                    st.success("تم تسجيل حالة الحضور.")
                except sqlite3.IntegrityError:
                    q("UPDATE attendance SET status=?, notes=? WHERE employee_id=? AND work_date=?",
                      (status, notes, emp_id, str(att_date)))
                    st.success("تم تحديث حالة حضور الموظف بنجاح.")
                    
        st.subheader("سجل الحضور الأخير")
        st.dataframe(get_df("SELECT e.name AS الموظف, a.work_date AS التاريخ, a.status AS الحالة, a.notes AS ملاحظات FROM attendance a JOIN employees e ON a.employee_id=e.id ORDER BY a.work_date DESC LIMIT 50"), use_container_width=True, hide_index=True)

# --- 7. الحسابات والقيود اليومية ---
elif choice == "💰 الحسابات والقيود اليومية":
    require_role(["مدير النظام", "محاسب"])
    st.markdown("<h2 class='main-header'>دفتر القيود المحاسبية اليومية (GL)</h2>", unsafe_allow_html=True)
    
    accounts = get_df("SELECT code, name FROM accounts")
    ccenters = get_df("SELECT id, name FROM cost_centers WHERE active=1")
    
    with st.form("manual_je"):
        desc = st.text_input("بيان القيد المحاسبي:")
        c1, c2, c3, c4 = st.columns(4)
        acc_dict = {f"{r['code']} - {r['name']}": r['code'] for _, r in accounts.iterrows()}
        cc_dict = {r['name']: r['id'] for _, r in ccenters.iterrows()}
        
        acc_dr = c1.selectbox("الحساب المدين", list(acc_dict.keys()))
        acc_cr = c2.selectbox("الحساب الدائن", list(acc_dict.keys()))
        amt = c3.number_input("المبلغ", min_value=1.0)
        cc = c4.selectbox("مركز التكلفة", ["بدون"] + list(cc_dict.keys()))
        
        if st.form_submit_button("ترحيل القيد المزدوج ✍️", type="primary"):
            if not desc: st.error("بيان القيد إلزامي.")
            elif acc_dr == acc_cr: st.error("لا يمكن أن يتطابق المدين والدائن.")
            else:
                cc_val = cc_dict[cc] if cc != "بدون" else None
                lines = [
                    {"acc": acc_dict[acc_dr], "debit": amt, "cc_id": cc_val},
                    {"acc": acc_dict[acc_cr], "credit": amt, "cc_id": cc_val}
                ]
                ok, m = post_journal(desc, lines)
                if ok: st.success(f"تم ترحيل القيد برقم {m}"); st.rerun()
                else: st.error(m)

# --- 8. التقارير المالية الختامية ---
elif choice == "📄 التقارير المالية الختامية":
    require_role(["مدير النظام", "محاسب"])
    st.markdown("<h2 class='main-header'>القوائم المالية الختامية</h2>", unsafe_allow_html=True)
    
    rep = st.selectbox("اختر التقرير الختامي:", ["ميزان المراجعة", "قائمة الدخل (الأرباح والخسائر)"])
    
    if rep == "ميزان المراجعة":
        df = get_df("""
            SELECT a.code AS رقم_الحساب, a.name AS اسم_الحساب, a.account_type AS التصنيف, 
                   COALESCE(SUM(l.debit),0) AS إجمالي_المدين, COALESCE(SUM(l.credit),0) AS إجمالي_الدائن,
                   COALESCE(SUM(l.debit),0) - COALESCE(SUM(l.credit),0) AS الرصيد
            FROM accounts a LEFT JOIN journal_lines l ON a.code=l.account_code 
            GROUP BY a.code HAVING إجمالي_المدين > 0 OR إجمالي_الدائن > 0
        """)
        st.dataframe(df, use_container_width=True, hide_index=True)
        
    elif rep == "قائمة الدخل (الأرباح والخسائر)":
        df = get_df("""
            SELECT a.name AS البند, a.account_type AS التصنيف, SUM(l.credit) - SUM(l.debit) AS القيمة 
            FROM accounts a JOIN journal_lines l ON a.code=l.account_code 
            WHERE a.account_type IN ('إيرادات','مصروفات') GROUP BY a.code
        """)
        if not df.empty:
            df.loc[df['التصنيف'] == 'مصروفات', 'القيمة'] *= -1
            st.dataframe(df, use_container_width=True, hide_index=True)
            net = df[df['التصنيف'] == 'إيرادات']['القيمة'].sum() - df[df['التصنيف'] == 'مصروفات']['القيمة'].sum()
            st.metric("صافي الربح / (الخسارة) الصافي", f"{money(net)} {BASE_CURRENCY}")

# --- 9. إعدادات النظام والصلاحيات ---
elif choice == "⚙️ إعدادات النظام والصلاحيات":
    require_role(["مدير النظام"])
    st.markdown("<h2 class='main-header'>لوحة التحكم الإدارية والصلاحيات</h2>", unsafe_allow_html=True)
    
    t1, t2 = st.tabs(["🔑 إدارة المستخدمين وصلاحياتهم (RBAC)", "🏢 بيانات الشركة"])
    
    with t1:
        with st.form("new_user"):
            c1, c2 = st.columns(2)
            u_name = c1.text_input("اسم المستخدم للدخول")
            f_name = c2.text_input("الاسم الكامل")
            c3, c4 = st.columns(2)
            role = c3.selectbox("الصلاحية الممنوحة:", ROLES)
            pwd = c4.text_input("كلمة المرور:", type="password")
            
            if st.form_submit_button("إنشاء حساب مستخدم"):
                if u_name and pwd:
                    try:
                        q("INSERT INTO users(username, password_hash, full_name, role) VALUES(?,?,?,?)",
                          (u_name, hash_password(pwd), f_name, role))
                        st.success("تم إنشاء حساب المستخدم بنجاح.")
                        st.rerun()
                    except sqlite3.IntegrityError: st.error("اسم المستخدم مسجل مسبقاً.")
                else: st.error("اسم المستخدم وكلمة المرور إجباريان.")
        st.dataframe(get_df("SELECT username AS المستخدم, full_name AS الاسم, role AS الصلاحية FROM users"), use_container_width=True, hide_index=True)
        
    with t2:
        with st.form("comp_update"):
            cname = st.text_input("اسم المؤسسة", value=comp_info['name'])
            ctax = st.text_input("الرقم الضريبي", value=comp_info['tax_no'])
            if st.form_submit_button("تحديث بيانات الشركة"):
                q("UPDATE company_info SET name=?, tax_no=? WHERE id=1", (cname, ctax))
                st.success("تم التحديث.")
                st.rerun()
