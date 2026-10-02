"""
SUPER ERP SYSTEM - PRO EDITION (V4)
نظام احترافي بواجهة عصرية، صلاحيات متقدمة، ومراكز تكلفة.
"""
import sqlite3, hashlib, os
from datetime import datetime, date
from contextlib import contextmanager
import pandas as pd
import streamlit as st

# ==========================================
# 0. إعدادات الصفحة والتصميم (CSS & UI)
# ==========================================
st.set_page_config(page_title="SUPER ERP PRO", page_icon="🏢", layout="wide", initial_sidebar_state="expanded")

# تصميم CSS مخصص لجمال المظهر والخطوط العربية
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
        box-shadow: 0 4px 8px rgba(0,0,0,0.1);
    }
    .main-header {
        color: #1f77b4;
        border-bottom: 2px solid #f0f2f6;
        padding-bottom: 10px;
        margin-bottom: 20px;
    }
    </style>
""", unsafe_allow_html=True)

# ==========================================
# 1. إعدادات قاعدة البيانات (V4)
# ==========================================
DB_FILE = os.getenv("ERP_DB", "super_erp_v4.db")
ROLES = ["مدير النظام", "محاسب", "موظف مبيعات", "مدير مشتريات", "مدير موارد بشرية"]
BASE_CURRENCY = "YER"

def now(): return datetime.now().isoformat(timespec="seconds")
def money(v): return f"{float(v or 0):,.2f}"
def next_no(prefix): return f"{prefix}-{datetime.now().strftime('%y%m%d%H%M')}"
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
        CREATE TABLE IF NOT EXISTS invoices(
            id INTEGER PRIMARY KEY AUTOINCREMENT, invoice_no TEXT UNIQUE, invoice_type TEXT, 
            total REAL, created_at TEXT, user_id INTEGER);
        CREATE TABLE IF NOT EXISTS employees(
            id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, department TEXT, basic_salary REAL);
        CREATE TABLE IF NOT EXISTS accounts(
            code TEXT PRIMARY KEY, name TEXT, account_type TEXT);
        CREATE TABLE IF NOT EXISTS journal_entries(
            id INTEGER PRIMARY KEY AUTOINCREMENT, entry_no TEXT UNIQUE, date TEXT, description TEXT, user_id INTEGER);
        CREATE TABLE IF NOT EXISTS journal_lines(
            id INTEGER PRIMARY KEY AUTOINCREMENT, entry_id INTEGER, account_code TEXT, cost_center_id INTEGER,
            debit REAL DEFAULT 0, credit REAL DEFAULT 0, currency_code TEXT, exchange_rate REAL);
        """)
        
        # الإعدادات الافتراضية
        if c.execute("SELECT COUNT(*) FROM company_info").fetchone()[0] == 0:
            c.execute("INSERT INTO company_info (id, name, tax_no) VALUES (1, 'مؤسسة يمن سوفت للتجارة', '100200300')")
        if c.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0:
            c.execute("INSERT INTO users(username, password_hash, full_name, role) VALUES(?,?,?,?)",
                      ("admin", hash_password("admin"), "المدير العام", "مدير النظام"))
        if c.execute("SELECT COUNT(*) FROM currencies").fetchone()[0] == 0:
            c.executemany("INSERT INTO currencies VALUES(?,?,?)", [("YER", "ريال يمني", 1.0), ("USD", "دولار أمريكي", 530.0), ("SAR", "ريال سعودي", 140.0)])
        if c.execute("SELECT COUNT(*) FROM cost_centers").fetchone()[0] == 0:
            c.executemany("INSERT INTO cost_centers(name) VALUES(?)", [("المركز الرئيسي - صنعاء",), ("فرع عدن",)])
        if c.execute("SELECT COUNT(*) FROM accounts").fetchone()[0] == 0:
            accounts = [("101","الصندوق","أصول"),("102","البنك","أصول"),("103","المخزون","أصول"),
                        ("301","رأس المال","حقوق ملكية"),("401","إيرادات المبيعات","إيرادات"),
                        ("501","تكلفة المبيعات","مصروفات"),("502","الرواتب","مصروفات"),("503","مصروفات تشغيلية","مصروفات")]
            c.executemany("INSERT INTO accounts VALUES(?,?,?)", accounts)

# ==========================================
# 2. نظام التحقق من الصلاحيات
# ==========================================
def require_role(allowed_roles):
    if st.session_state.role not in allowed_roles:
        st.error(f"🔒 عذراً {st.session_state.full_name}، صلاحية '{st.session_state.role}' لا تسمح بالوصول لهذه النافذة.")
        st.stop()

def post_journal(desc, lines):
    debit = round(sum(float(x.get("debit", 0)) for x in lines), 2)
    credit = round(sum(float(x.get("credit", 0)) for x in lines), 2)
    if debit != credit: return False, f"القيد غير متزن (الفرق: {debit - credit})"
    
    entry_no = next_no("JE")
    with get_db() as c:
        eid = c.execute("INSERT INTO journal_entries(entry_no, date, description, user_id) VALUES(?,?,?,?)",
                        (entry_no, date.today().isoformat(), desc, st.session_state.user_id)).lastrowid
        for x in lines:
            c.execute("INSERT INTO journal_lines(entry_id, account_code, cost_center_id, debit, credit, currency_code, exchange_rate) VALUES(?,?,?,?,?,?,?)",
                      (eid, x["acc"], x.get("cc_id"), x.get("debit",0), x.get("credit",0), x.get("currency","YER"), x.get("rate",1)))
    return True, entry_no

# ==========================================
# 3. المصادقة (تسجيل الدخول)
# ==========================================
init_db()
if "logged_in" not in st.session_state: st.session_state.logged_in = False

if not st.session_state.logged_in:
    col1, col2, col3 = st.columns([1,2,1])
    with col2:
        st.markdown("<h1 style='text-align: center; color: #1f77b4;'>🏢 نظام SUPER ERP PRO</h1>", unsafe_allow_html=True)
        st.markdown("<p style='text-align: center;'>النسخة المؤسسية - تسجيل الدخول</p>", unsafe_allow_html=True)
        with st.form("login_form"):
            username = st.text_input("👤 اسم المستخدم", placeholder="أدخل اسم المستخدم...")
            password = st.text_input("🔑 كلمة المرور", type="password", placeholder="أدخل كلمة المرور...")
            submit = st.form_submit_button("تسجيل الدخول 🚀", use_container_width=True)
            
        if submit:
            user_data = q("SELECT * FROM users WHERE username=? AND active=1", (username,))
            if user_data and user_data[0]["password_hash"] == hash_password(password):
                st.session_state.update(logged_in=True, user_id=user_data[0]["id"], username=username, 
                                        full_name=user_data[0]["full_name"], role=user_data[0]["role"])
                st.rerun()
            else: 
                st.error("❌ بيانات الدخول غير صحيحة أو الحساب موقوف.")
    st.stop()

# ==========================================
# 4. الهيكل الأساسي والقائمة الجانبية
# ==========================================
comp_info = q("SELECT * FROM company_info WHERE id=1")[0]
st.sidebar.markdown(f"<h3 style='text-align:center;'>{comp_info['name']}</h3>", unsafe_allow_html=True)
st.sidebar.markdown(f"<p style='text-align:center; color:gray;'>مرحباً: {st.session_state.full_name}<br>({st.session_state.role})</p>", unsafe_allow_html=True)
st.sidebar.divider()

menu = ["📊 لوحة القيادة", "🛒 المبيعات", "📦 المشتريات والمخزون", "👥 الموارد البشرية", "💰 الإدارة المالية", "📄 التقارير الشاملة", "⚙️ إعدادات النظام"]
choice = st.sidebar.radio("القائمة الرئيسية:", menu)

if st.sidebar.button("🚪 تسجيل الخروج", use_container_width=True):
    st.session_state.clear()
    st.rerun()

# ==========================================
# 5. برمجة النوافذ (Modules)
# ==========================================

# --- 1. لوحة القيادة ---
if choice == "📊 لوحة القيادة":
    st.markdown("<h2 class='main-header'>لوحة المؤشرات التنفيذية</h2>", unsafe_allow_html=True)
    
    col1, col2, col3, col4 = st.columns(4)
    sales = get_df("SELECT SUM(total) as t FROM invoices WHERE invoice_type='بيع'")['t'].sum() or 0
    prods = get_df("SELECT COUNT(*) as c FROM products")['c'].sum() or 0
    emps = get_df("SELECT COUNT(*) as c FROM employees")['c'].sum() or 0
    
    col1.metric("إجمالي المبيعات", f"{money(sales)} {BASE_CURRENCY}")
    col2.metric("عدد المنتجات", int(prods))
    col3.metric("عدد الموظفين", int(emps))
    col4.metric("حالة النظام", "مستقر 🟢")
    
    st.divider()
    st.subheader("آخر الحركات المالية")
    df_jl = get_df("SELECT entry_no AS القيد, date AS التاريخ, description AS البيان FROM journal_entries ORDER BY id DESC LIMIT 5")
    st.dataframe(df_jl, use_container_width=True, hide_index=True)

# --- 2. المبيعات ---
elif choice == "🛒 المبيعات":
    require_role(["مدير النظام", "موظف مبيعات", "محاسب"])
    st.markdown("<h2 class='main-header'>نافذة المبيعات (نقاط البيع)</h2>", unsafe_allow_html=True)
    
    products = get_df("SELECT id, sku, name, sale_price, cost_price, stock_qty FROM products WHERE active=1")
    if products.empty:
        st.warning("لا توجد منتجات مسجلة. الرجاء إضافتها من شاشة المخزون أولاً.")
    else:
        with st.form("pos_form"):
            col1, col2 = st.columns([2,1])
            prod_dict = {f"{r['sku']} - {r['name']} (متاح: {r['stock_qty']})": r for _, r in products.iterrows()}
            selected = col1.selectbox("اختر الصنف:", list(prod_dict.keys()))
            qty = col2.number_input("الكمية المباعة:", min_value=1, value=1)
            
            submit = st.form_submit_button("إصدار فاتورة بيع وترحيلها 🧾", type="primary")
            
            if submit:
                p = prod_dict[selected]
                if qty > p['stock_qty']:
                    st.error("الكمية المطلوبة تتجاوز رصيد المخزون المتوفر!")
                else:
                    t_sale = qty * p['sale_price']
                    t_cost = qty * p['cost_price']
                    inv_no = next_no("SAL")
                    
                    with get_db() as c:
                        c.execute("UPDATE products SET stock_qty = stock_qty - ? WHERE id=?", (qty, p['id']))
                        c.execute("INSERT INTO invoices(invoice_no, invoice_type, total, created_at, user_id) VALUES(?,?,?,?,?)",
                                  (inv_no, "بيع", t_sale, now(), st.session_state.user_id))
                    
                    lines = [
                        {"acc": "101", "debit": t_sale}, {"acc": "401", "credit": t_sale},
                        {"acc": "501", "debit": t_cost}, {"acc": "103", "credit": t_cost}
                    ]
                    post_journal(f"فاتورة مبيعات {inv_no}", lines)
                    st.success(f"تم البيع بنجاح! إجمالي الفاتورة: {money(t_sale)}")
                    st.rerun()

# --- 3. المشتريات والمخزون ---
elif choice == "📦 المشتريات والمخزون":
    require_role(["مدير النظام", "مدير مشتريات", "محاسب"])
    st.markdown("<h2 class='main-header'>إدارة المخزون والمشتريات</h2>", unsafe_allow_html=True)
    
    t1, t2 = st.tabs(["إضافة/تعديل صنف", "سجل المخزون اللحظي"])
    with t1:
        with st.form("new_product"):
            c1, c2 = st.columns(2)
            sku = c1.text_input("رمز الصنف (SKU)")
            name = c2.text_input("اسم الصنف")
            c3, c4 = st.columns(2)
            cost = c3.number_input("تكلفة الشراء", min_value=0.0)
            sale = c4.number_input("سعر البيع الافتراضي", min_value=0.0)
            opening = st.number_input("الرصيد الافتتاحي بالمخزن", min_value=0.0)
            
            if st.form_submit_button("حفظ الصنف"):
                if name and sku:
                    try:
                        q("INSERT INTO products(sku,name,cost_price,sale_price,stock_qty) VALUES(?,?,?,?,?)",
                          (sku, name, cost, sale, opening))
                        st.success("تمت الإضافة بنجاح.")
                        st.rerun()
                    except sqlite3.IntegrityError:
                        st.error("رمز الصنف مسجل مسبقاً!")
                else:
                    st.error("الرمز والاسم حقول إجبارية.")
    with t2:
        df = get_df("SELECT sku AS الرمز, name AS الصنف, cost_price AS التكلفة, sale_price AS سعر_البيع, stock_qty AS الرصيد_الحالي FROM products")
        st.dataframe(df, use_container_width=True, hide_index=True)

# --- 4. الموارد البشرية ---
elif choice == "👥 الموارد البشرية":
    require_role(["مدير النظام", "مدير موارد بشرية"])
    st.markdown("<h2 class='main-header'>شؤون الموظفين والرواتب</h2>", unsafe_allow_html=True)
    
    with st.form("new_emp"):
        col1, col2, col3 = st.columns(3)
        emp_name = col1.text_input("اسم الموظف")
        emp_dept = col2.selectbox("القسم", ["الإدارة", "المبيعات", "المحاسبة", "التشغيل"])
        emp_sal = col3.number_input("الراتب الأساسي", min_value=10000.0, step=1000.0)
        if st.form_submit_button("إضافة الموظف"):
            if emp_name:
                q("INSERT INTO employees(name,department,basic_salary) VALUES(?,?,?)", (emp_name, emp_dept, emp_sal))
                st.success("تم الحفظ")
                st.rerun()
            else: st.error("اسم الموظف مطلوب")
            
    st.subheader("سجل الموظفين")
    df_emps = get_df("SELECT id, name AS الموظف, department AS القسم, basic_salary AS الراتب FROM employees")
    st.dataframe(df_emps, use_container_width=True, hide_index=True)

# --- 5. الإدارة المالية ---
elif choice == "💰 الإدارة المالية":
    require_role(["مدير النظام", "محاسب"])
    st.markdown("<h2 class='main-header'>دفتر قيود اليومية العامة</h2>", unsafe_allow_html=True)
    
    accounts = get_df("SELECT code, name FROM accounts")
    ccenters = get_df("SELECT id, name FROM cost_centers WHERE active=1")
    
    with st.form("manual_je"):
        desc = st.text_input("بيان القيد (المرجع الدفتري)")
        c1, c2, c3, c4 = st.columns(4)
        acc_dict = {f"{r['code']} - {r['name']}": r['code'] for _, r in accounts.iterrows()}
        cc_dict = {r['name']: r['id'] for _, r in ccenters.iterrows()}
        
        acc_dr = c1.selectbox("الحساب المدين", list(acc_dict.keys()))
        acc_cr = c2.selectbox("الحساب الدائن", list(acc_dict.keys()))
        amt = c3.number_input("المبلغ", min_value=1.0)
        cc = c4.selectbox("مركز التكلفة (اختياري)", ["بدون"] + list(cc_dict.keys()))
        
        if st.form_submit_button("ترحيل القيد المحاسبي المزدوج ✍️", type="primary"):
            if not desc: st.error("بيان القيد الزامي للتدقيق.")
            elif acc_dr == acc_cr: st.error("لا يمكن أن يكون المدين والدائن نفس الحساب.")
            else:
                cc_val = cc_dict[cc] if cc != "بدون" else None
                lines = [
                    {"acc": acc_dict[acc_dr], "debit": amt, "cc_id": cc_val},
                    {"acc": acc_dict[acc_cr], "credit": amt, "cc_id": cc_val}
                ]
                ok, m = post_journal(desc, lines)
                if ok: st.success(f"تم ترحيل القيد برقم {m}"); st.rerun()
                else: st.error(m)

# --- 6. التقارير الشاملة ---
elif choice == "📄 التقارير الشاملة":
    require_role(["مدير النظام", "محاسب"])
    st.markdown("<h2 class='main-header'>التقارير والكشوفات المالية</h2>", unsafe_allow_html=True)
    
    rep_type = st.selectbox("اختر التقرير المالي:", ["ميزان المراجعة", "قائمة الدخل", "كشف حساب (أستاذ مساعد)"])
    
    if rep_type == "ميزان المراجعة":
        df = get_df("""
            SELECT a.code AS رقم_الحساب, a.name AS اسم_الحساب, a.account_type AS النوع, 
                   COALESCE(SUM(l.debit),0) AS إجمالي_المدين, COALESCE(SUM(l.credit),0) AS إجمالي_الدائن,
                   COALESCE(SUM(l.debit),0) - COALESCE(SUM(l.credit),0) AS الرصيد
            FROM accounts a LEFT JOIN journal_lines l ON a.code=l.account_code 
            GROUP BY a.code HAVING إجمالي_المدين > 0 OR إجمالي_الدائن > 0
        """)
        st.dataframe(df, use_container_width=True, hide_index=True)
        
    elif rep_type == "قائمة الدخل":
        df = get_df("""
            SELECT a.name AS البند, a.account_type AS التصنيف, SUM(l.credit) - SUM(l.debit) AS صافي_القيمة 
            FROM accounts a JOIN journal_lines l ON a.code=l.account_code 
            WHERE a.account_type IN ('إيرادات','مصروفات') GROUP BY a.code
        """)
        if not df.empty:
            df.loc[df['التصنيف'] == 'مصروفات', 'صافي_القيمة'] *= -1
            st.dataframe(df, use_container_width=True, hide_index=True)
            net = df[df['التصنيف'] == 'إيرادات']['صافي_القيمة'].sum() - df[df['التصنيف'] == 'مصروفات']['صافي_القيمة'].sum()
            st.metric("صافي الربح / (الخسارة) للفترة", f"{money(net)} {BASE_CURRENCY}")

# --- 7. إعدادات النظام المتقدمة ---
elif choice == "⚙️ إعدادات النظام":
    require_role(["مدير النظام"])
    st.markdown("<h2 class='main-header'>لوحة تحكم النظام والحوكمة</h2>", unsafe_allow_html=True)
    
    t1, t2, t3 = st.tabs(["🏢 بيانات الشركة (Profile)", "🔑 إدارة المستخدمين والصلاحيات", "🏛️️ مراكز التكلفة للفروع"])
    
    with t1:
        st.subheader("ترويسة المؤسسة للتقارير")
        with st.form("company_form"):
            cname = st.text_input("اسم المؤسسة القانوني", value=comp_info['name'])
            ctax = st.text_input("الرقم الضريبي", value=comp_info['tax_no'])
            caddr = st.text_area("العنوان", value=comp_info['address'] if comp_info['address'] else "")
            cphone = st.text_input("الهاتف", value=comp_info['phone'] if comp_info['phone'] else "")
            if st.form_submit_button("حفظ بيانات المؤسسة", type="primary"):
                q("UPDATE company_info SET name=?, tax_no=?, address=?, phone=? WHERE id=1", (cname, ctax, caddr, cphone))
                st.success("تم التحديث. ستظهر هذه البيانات في ترويسة التقارير.")
                st.rerun()

    with t2:
        st.subheader("نظام الحوكمة للمستخدمين (RBAC)")
        with st.form("new_user"):
            c1, c2 = st.columns(2)
            u_name = c1.text_input("اسم الدخول (Username)")
            f_name = c2.text_input("الاسم الكامل للموظف")
            c3, c4 = st.columns(2)
            role = c3.selectbox("الصلاحية الممنوحة", ROLES)
            pwd = c4.text_input("كلمة المرور المؤقتة", type="password")
            if st.form_submit_button("إنشاء حساب مستخدم جديد"):
                if u_name and pwd:
                    try:
                        q("INSERT INTO users(username,password_hash,full_name,role) VALUES(?,?,?,?)",
                          (u_name, hash_password(pwd), f_name, role))
                        st.success("تم إنشاء الحساب.")
                        st.rerun()
                    except sqlite3.IntegrityError: st.error("اسم المستخدم هذا مستخدم مسبقاً.")
                else: st.error("الاسم وكلمة المرور مطلوبان.")
        
        st.dataframe(get_df("SELECT username AS المستخدم, full_name AS الاسم, role AS الصلاحية FROM users"), use_container_width=True, hide_index=True)
        
    with t3:
        st.subheader("تعريف الفروع ومراكز التكلفة")
        st.info("مراكز التكلفة تساعدك على فصل أرباح ومصروفات كل فرع أو مشروع على حدة.")
        cc_name = st.text_input("اسم المركز / الفرع الجديد")
        if st.button("اعتماد المركز المالي"):
            if cc_name:
                try:
                    q("INSERT INTO cost_centers(name) VALUES(?)", (cc_name,))
                    st.success("تم تسجيل المركز.")
                    st.rerun()
                except sqlite3.IntegrityError: st.error("هذا المركز مسجل مسبقاً.")
        
        st.dataframe(get_df("SELECT id AS الكود, name AS اسم_المركز FROM cost_centers"), use_container_width=True, hide_index=True)
