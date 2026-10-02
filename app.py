"""
SUPER ERP SYSTEM - Arabic Streamlit Edition
نسخة موسعة قابلة للتطوير لنظام ERP تجاري.
التشغيل: pip install streamlit pandas passlib[bcrypt] ثم streamlit run super_erp_expanded.py
"""
import sqlite3, hashlib, os
from datetime import datetime, date
from contextlib import contextmanager
import pandas as pd
import streamlit as st

DB_FILE = os.getenv("ERP_DB", "super_erp_system.db")
ROLES = ["مدير النظام", "محاسب", "موظف مبيعات", "مدير مشتريات", "مدير موارد بشرية", "مراقب مخزون"]
BASE_CURRENCY = "SAR"

st.set_page_config(page_title="SUPER ERP", page_icon="📊", layout="wide", initial_sidebar_state="expanded")

# -----------------------------------------------------------------------------
# قاعدة البيانات
# -----------------------------------------------------------------------------
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

def one(sql, params=()):
    rows = q(sql, params)
    return rows[0] if rows else None

def scalar(sql, params=()):
    row = one(sql, params)
    return list(row)[0] if row else 0

def hash_password(password):
    return hashlib.sha256(password.encode("utf-8")).hexdigest()

def init_db():
    with get_db() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS users(
            id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL, full_name TEXT, role TEXT NOT NULL,
            active INTEGER DEFAULT 1, created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS currencies(
            code TEXT PRIMARY KEY, name TEXT NOT NULL, symbol TEXT,
            exchange_rate REAL NOT NULL DEFAULT 1, active INTEGER DEFAULT 1);
        CREATE TABLE IF NOT EXISTS categories(
            id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE NOT NULL);
        CREATE TABLE IF NOT EXISTS products(
            id INTEGER PRIMARY KEY AUTOINCREMENT, sku TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL, category_id INTEGER, unit TEXT DEFAULT 'قطعة',
            cost_price REAL DEFAULT 0, sale_price REAL DEFAULT 0,
            stock_qty REAL DEFAULT 0, min_stock REAL DEFAULT 0, tax_rate REAL DEFAULT 0,
            active INTEGER DEFAULT 1, created_at TEXT NOT NULL,
            FOREIGN KEY(category_id) REFERENCES categories(id));
        CREATE TABLE IF NOT EXISTS contacts(
            id INTEGER PRIMARY KEY AUTOINCREMENT, kind TEXT NOT NULL,
            code TEXT UNIQUE, name TEXT NOT NULL, phone TEXT, email TEXT,
            address TEXT, tax_no TEXT, opening_balance REAL DEFAULT 0,
            active INTEGER DEFAULT 1, created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS warehouses(
            id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE NOT NULL, location TEXT);
        CREATE TABLE IF NOT EXISTS stock_movements(
            id INTEGER PRIMARY KEY AUTOINCREMENT, product_id INTEGER NOT NULL,
            warehouse_id INTEGER, movement_type TEXT NOT NULL, quantity REAL NOT NULL,
            unit_cost REAL DEFAULT 0, reference TEXT, notes TEXT, created_at TEXT NOT NULL,
            user_id INTEGER, FOREIGN KEY(product_id) REFERENCES products(id),
            FOREIGN KEY(warehouse_id) REFERENCES warehouses(id));
        CREATE TABLE IF NOT EXISTS invoices(
            id INTEGER PRIMARY KEY AUTOINCREMENT, invoice_no TEXT UNIQUE NOT NULL,
            invoice_type TEXT NOT NULL, contact_id INTEGER, warehouse_id INTEGER,
            currency_code TEXT DEFAULT 'SAR', exchange_rate REAL DEFAULT 1,
            subtotal REAL DEFAULT 0, discount REAL DEFAULT 0, tax REAL DEFAULT 0,
            total REAL DEFAULT 0, paid REAL DEFAULT 0, status TEXT DEFAULT 'مكتملة',
            notes TEXT, created_at TEXT NOT NULL, user_id INTEGER,
            FOREIGN KEY(contact_id) REFERENCES contacts(id));
        CREATE TABLE IF NOT EXISTS invoice_lines(
            id INTEGER PRIMARY KEY AUTOINCREMENT, invoice_id INTEGER NOT NULL,
            product_id INTEGER NOT NULL, quantity REAL NOT NULL, unit_price REAL NOT NULL,
            discount REAL DEFAULT 0, tax REAL DEFAULT 0,
            FOREIGN KEY(invoice_id) REFERENCES invoices(id) ON DELETE CASCADE,
            FOREIGN KEY(product_id) REFERENCES products(id));
        CREATE TABLE IF NOT EXISTS employees(
            id INTEGER PRIMARY KEY AUTOINCREMENT, employee_no TEXT UNIQUE,
            name TEXT NOT NULL, department TEXT, job_title TEXT, phone TEXT,
            basic_salary REAL DEFAULT 0, hire_date TEXT, active INTEGER DEFAULT 1);
        CREATE TABLE IF NOT EXISTS attendance(
            id INTEGER PRIMARY KEY AUTOINCREMENT, employee_id INTEGER NOT NULL,
            work_date TEXT NOT NULL, status TEXT NOT NULL, notes TEXT,
            UNIQUE(employee_id, work_date));
        CREATE TABLE IF NOT EXISTS expenses(
            id INTEGER PRIMARY KEY AUTOINCREMENT, expense_no TEXT UNIQUE,
            title TEXT NOT NULL, category TEXT, amount REAL NOT NULL,
            currency_code TEXT DEFAULT 'SAR', paid_from TEXT DEFAULT 'الصندوق',
            notes TEXT, created_at TEXT NOT NULL, user_id INTEGER);
        CREATE TABLE IF NOT EXISTS accounts(
            code TEXT PRIMARY KEY, name TEXT NOT NULL, account_type TEXT NOT NULL,
            parent_code TEXT, active INTEGER DEFAULT 1);
        CREATE TABLE IF NOT EXISTS journal_entries(
            id INTEGER PRIMARY KEY AUTOINCREMENT, entry_no TEXT UNIQUE,
            entry_date TEXT NOT NULL, description TEXT NOT NULL,
            reference TEXT, posted INTEGER DEFAULT 1, user_id INTEGER, created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS journal_lines(
            id INTEGER PRIMARY KEY AUTOINCREMENT, entry_id INTEGER NOT NULL,
            account_code TEXT NOT NULL, debit REAL DEFAULT 0, credit REAL DEFAULT 0,
            currency_code TEXT DEFAULT 'SAR', foreign_amount REAL DEFAULT 0,
            exchange_rate REAL DEFAULT 1,
            FOREIGN KEY(entry_id) REFERENCES journal_entries(id) ON DELETE CASCADE,
            FOREIGN KEY(account_code) REFERENCES accounts(code));
        CREATE TABLE IF NOT EXISTS audit_log(
            id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, action TEXT,
            entity TEXT, entity_id INTEGER, details TEXT, created_at TEXT NOT NULL);
        """)
        # توافق مع قاعدة البيانات القديمة التي كانت تحتوي password و role فقط.
        user_columns = {row[1] for row in c.execute("PRAGMA table_info(users)").fetchall()}
        legacy_columns = {
            "password_hash": "TEXT",
            "full_name": "TEXT",
            "active": "INTEGER DEFAULT 1",
            "created_at": "TEXT DEFAULT ''",
        }
        for column, definition in legacy_columns.items():
            if column not in user_columns:
                c.execute(f"ALTER TABLE users ADD COLUMN {column} {definition}")
        if "password" in user_columns:
            old_users = c.execute("SELECT id, password FROM users WHERE password_hash IS NULL OR password_hash='' ").fetchall()
            for old_user in old_users:
                c.execute("UPDATE users SET password_hash=?, full_name=COALESCE(full_name, username), active=1, created_at=COALESCE(NULLIF(created_at,''), ?) WHERE id=?",
                          (hash_password(old_user[1] or ""), now(), old_user[0]))
        if c.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0:
            c.execute("INSERT INTO users(username,password_hash,full_name,role,created_at) VALUES(?,?,?,?,?)",
                      ("admin", hash_password("admin"), "مدير النظام", "مدير النظام", now()))
        if c.execute("SELECT COUNT(*) FROM currencies").fetchone()[0] == 0:
            c.executemany("INSERT INTO currencies(code,name,symbol,exchange_rate) VALUES(?,?,?,?)", [
                ("SAR", "ريال سعودي", "ر.س", 1), ("YER", "ريال يمني", "ر.ي", 0.0071), ("USD", "دولار أمريكي", "$", 3.75)])
        if c.execute("SELECT COUNT(*) FROM categories").fetchone()[0] == 0:
            c.executemany("INSERT INTO categories(name) VALUES(?)", [("إلكترونيات",),("مكتبيات",),("مواد استهلاكية",)])
        if c.execute("SELECT COUNT(*) FROM warehouses").fetchone()[0] == 0:
            c.execute("INSERT INTO warehouses(name,location) VALUES(?,?)", ("المستودع الرئيسي", "المقر الرئيسي"))
        if c.execute("SELECT COUNT(*) FROM accounts").fetchone()[0] == 0:
            accounts = [("101","الصندوق","أصول"),("102","البنك","أصول"),("103","المخزون","أصول"),
                        ("104","العملاء","أصول"),("201","الموردون","خصوم"),("301","رأس المال","حقوق ملكية"),
                        ("401","إيرادات المبيعات","إيرادات"),("402","إيرادات أخرى","إيرادات"),
                        ("501","تكلفة المبيعات","مصروفات"),("502","مصروفات الرواتب","مصروفات"),
                        ("503","المصروفات التشغيلية","مصروفات"),("504","فروق العملات","مصروفات")]
            c.executemany("INSERT INTO accounts(code,name,account_type) VALUES(?,?,?)", accounts)
        if c.execute("SELECT COUNT(*) FROM products").fetchone()[0] == 0:
            t = now(); c.executemany("""INSERT INTO products
                (sku,name,category_id,unit,cost_price,sale_price,stock_qty,min_stock,created_at)
                VALUES(?,?,?,?,?,?,?,?,?)""", [("PRD-001","حاسوب محمول",1,"قطعة",700,850,12,3,t),
                ("PRD-002","طابعة مكتبية",1,"قطعة",175,220,7,2,t), ("PRD-003","ورق A4",2,"كرتون",5,8,35,10,t)])

def now(): return datetime.now().isoformat(timespec="seconds")
def money(v): return f"{float(v or 0):,.2f}"
def next_no(prefix): return f"{prefix}-{datetime.now().strftime('%Y%m%d%H%M%S%f')}"

def audit(action, entity, entity_id=None, details=""):
    uid = st.session_state.get("user_id")
    q("INSERT INTO audit_log(user_id,action,entity,entity_id,details,created_at) VALUES(?,?,?,?,?,?)", (uid,action,entity,entity_id,details,now()))

def post_journal(description, lines, reference=""):
    debit = round(sum(float(x.get("debit",0)) for x in lines),2)
    credit = round(sum(float(x.get("credit",0)) for x in lines),2)
    if debit != credit: return False, f"القيد غير متزن: مدين {debit} / دائن {credit}"
    entry_no = next_no("JE")
    with get_db() as c:
        entry_id = c.execute("INSERT INTO journal_entries(entry_no,entry_date,description,reference,user_id,created_at) VALUES(?,?,?,?,?,?)",
                             (entry_no,date.today().isoformat(),description,reference,st.session_state.get("user_id"),now())).lastrowid
        for x in lines:
            c.execute("INSERT INTO journal_lines(entry_id,account_code,debit,credit,currency_code,foreign_amount,exchange_rate) VALUES(?,?,?,?,?,?,?)",
                      (entry_id,x["account"],x.get("debit",0),x.get("credit",0),x.get("currency","SAR"),x.get("foreign_amount",0),x.get("rate",1)))
    return True, entry_no

def record_stock(product_id, qty, movement_type, unit_cost=0, reference="", notes=""):
    sign = 1 if movement_type in ("شراء","إدخال","مرتجع بيع","تسوية زيادة") else -1
    with get_db() as c:
        c.execute("UPDATE products SET stock_qty=stock_qty+? WHERE id=?", (sign*qty,product_id))
        c.execute("INSERT INTO stock_movements(product_id,movement_type,quantity,unit_cost,reference,notes,created_at,user_id) VALUES(?,?,?,?,?,?,?,?)",
                  (product_id,movement_type,sign*qty,unit_cost,reference,notes,now(),st.session_state.get("user_id")))

def can(*roles): return st.session_state.get("role") in roles

# -----------------------------------------------------------------------------
# المصادقة
# -----------------------------------------------------------------------------
init_db()
if "logged_in" not in st.session_state: st.session_state.logged_in = False
if not st.session_state.logged_in:
    st.title("🔐 SUPER ERP")
    st.caption("نظام تخطيط موارد المؤسسة متعدد الوحدات")
    with st.form("login"):
        username=st.text_input("اسم المستخدم", value="admin")
        password=st.text_input("كلمة المرور", type="password")
        submit=st.form_submit_button("دخول", type="primary")
    st.info("بيانات التجربة الأولى: admin / admin")
    if submit:
        u=one("SELECT * FROM users WHERE username=? AND active=1", (username,))
        if u and u["password_hash"] == hash_password(password):
            st.session_state.update(logged_in=True,user_id=u["id"],username=u["username"],full_name=u["full_name"],role=u["role"]); st.rerun()
        else: st.error("اسم المستخدم أو كلمة المرور غير صحيحة")
    st.stop()

# -----------------------------------------------------------------------------
# الواجهة العامة
# -----------------------------------------------------------------------------
st.sidebar.title("SUPER ERP")
st.sidebar.write(f"مرحباً **{st.session_state.full_name or st.session_state.username}**")
st.sidebar.caption(f"الصلاحية: {st.session_state.role}")
if st.sidebar.button("تسجيل الخروج"):
    st.session_state.clear(); st.rerun()

pages=["لوحة المؤشرات","المبيعات","المشتريات","المخزون","العملاء والموردون","المصروفات","الموارد البشرية","المحاسبة","التقارير","الإعدادات"]
page=st.sidebar.radio("الوحدات",pages)

# لوحة المؤشرات
if page=="لوحة المؤشرات":
    st.title("📊 لوحة المؤشرات التنفيذية")
    products=scalar("SELECT COUNT(*) FROM products WHERE active=1"); customers=scalar("SELECT COUNT(*) FROM contacts WHERE kind='عميل' AND active=1")
    sales=scalar("SELECT COALESCE(SUM(total),0) FROM invoices WHERE invoice_type='بيع'"); expenses=scalar("SELECT COALESCE(SUM(amount),0) FROM expenses")
    low=scalar("SELECT COUNT(*) FROM products WHERE active=1 AND stock_qty<=min_stock")
    a,b,c,d,e=st.columns(5); a.metric("المنتجات",products); b.metric("العملاء",customers); c.metric("المبيعات",money(sales)); d.metric("المصروفات",money(expenses)); e.metric("تنبيه مخزون",low,delta_color="inverse")
    st.divider(); left,right=st.columns(2)
    with left:
        st.subheader("آخر الفواتير")
        df=pd.read_sql_query("""SELECT invoice_no AS الفاتورة,invoice_type AS النوع,total AS الإجمالي,status AS الحالة,created_at AS التاريخ FROM invoices ORDER BY id DESC LIMIT 10""", get_db().__enter__())
        st.dataframe(df,use_container_width=True,hide_index=True)
    with right:
        st.subheader("الأصناف منخفضة الرصيد")
        low_df=pd.read_sql_query("SELECT sku AS الرمز,name AS الصنف,stock_qty AS الرصيد,min_stock AS الحد_الأدنى FROM products WHERE stock_qty<=min_stock", get_db().__enter__())
        st.dataframe(low_df,use_container_width=True,hide_index=True)

# المبيعات والمشتريات المشتركة
elif page in ("المبيعات","المشتريات"):
    is_sale=page=="المبيعات"; title="💰 المبيعات والفواتير" if is_sale else "🛒 المشتريات والتوريد"
    allowed=("مدير النظام","محاسب","موظف مبيعات") if is_sale else ("مدير النظام","محاسب","مدير مشتريات")
    st.title(title)
    if not can(*allowed): st.warning("لا تملك الصلاحية للوصول إلى هذه الوحدة."); st.stop()
    products=q("SELECT * FROM products WHERE active=1 ORDER BY name")
    contacts=q("SELECT * FROM contacts WHERE kind=? AND active=1 ORDER BY name", ("عميل" if is_sale else "مورد",))
    with st.expander("إنشاء مستند جديد", expanded=True):
        with st.form("invoice_form"):
            c1,c2,c3=st.columns(3)
            pmap={f"{x['sku']} - {x['name']} (الرصيد {x['stock_qty']})":x for x in products}
            selected=c1.selectbox("الصنف",list(pmap) if pmap else ["لا توجد أصناف"])
            contact_map={f"{x['code'] or x['id']} - {x['name']}":x for x in contacts}
            selected_contact=c2.selectbox("الجهة",["نقدي / غير محدد"]+list(contact_map))
            qty=c3.number_input("الكمية",min_value=0.01,value=1.0,step=1.0)
            c4,c5,c6=st.columns(3)
            price=c4.number_input("سعر الوحدة",min_value=0.0,value=float(pmap[selected]["sale_price"] if is_sale and pmap and selected in pmap else (pmap[selected]["cost_price"] if pmap and selected in pmap else 0)),step=0.01)
            discount=c5.number_input("الخصم",min_value=0.0,value=0.0,step=0.01); tax=c6.number_input("الضريبة",min_value=0.0,value=0.0,step=0.01)
            notes=st.text_input("ملاحظات"); submit=st.form_submit_button("حفظ وترحيل",type="primary")
        if submit and pmap and selected in pmap:
            p=pmap[selected]; total=max(0,qty*price-discount)+tax
            if is_sale and p["stock_qty"]<qty: st.error("الرصيد المتاح لا يكفي"); st.stop()
            inv=next_no("SAL" if is_sale else "PUR"); contact_id=contact_map[selected_contact]["id"] if selected_contact in contact_map else None
            with get_db() as conn:
                iid=conn.execute("INSERT INTO invoices(invoice_no,invoice_type,contact_id,subtotal,discount,tax,total,notes,created_at,user_id) VALUES(?,?,?,?,?,?,?,?,?,?)",
                                  (inv,"بيع" if is_sale else "شراء",contact_id,qty*price,discount,tax,total,notes,now(),st.session_state.user_id)).lastrowid
                conn.execute("INSERT INTO invoice_lines(invoice_id,product_id,quantity,unit_price,discount,tax) VALUES(?,?,?,?,?,?)",(iid,p["id"],qty,price,discount,tax))
            record_stock(p["id"],qty,"بيع" if is_sale else "شراء",price,inv)
            if is_sale: post_journal(f"فاتورة بيع {inv}",[{"account":"101","debit":total},{"account":"401","credit":total}],inv)
            else: post_journal(f"فاتورة شراء {inv}",[{"account":"103","debit":total},{"account":"101","credit":total}],inv)
            audit("إنشاء", "فاتورة", iid, inv); st.success(f"تم حفظ المستند {inv}"); st.rerun()
    st.subheader("السجل")
    typ="بيع" if is_sale else "شراء"; df=pd.DataFrame(q("SELECT invoice_no AS الرقم,invoice_type AS النوع,total AS الإجمالي,status AS الحالة,created_at AS التاريخ FROM invoices WHERE invoice_type=? ORDER BY id DESC",(typ,)))
    st.dataframe(df,use_container_width=True,hide_index=True)

# المخزون
elif page=="المخزون":
    st.title("📦 إدارة المخزون")
    if not can("مدير النظام","محاسب","موظف مبيعات","مراقب مخزون"): st.warning("لا تملك الصلاحية"); st.stop()
    tab1,tab2,tab3=st.tabs(["الأرصدة","حركة المخزون","إضافة صنف"])
    with tab1:
        df=pd.DataFrame(q("""SELECT p.sku AS الرمز,p.name AS الصنف,COALESCE(c.name,'غير مصنف') AS التصنيف,p.unit AS الوحدة,p.cost_price AS التكلفة,p.sale_price AS البيع,p.stock_qty AS الرصيد,p.min_stock AS الحد_الأدنى FROM products p LEFT JOIN categories c ON c.id=p.category_id WHERE p.active=1""")); st.dataframe(df,use_container_width=True,hide_index=True)
    with tab2:
        df=pd.DataFrame(q("""SELECT m.created_at AS التاريخ,p.name AS الصنف,m.movement_type AS الحركة,m.quantity AS الكمية,m.reference AS المرجع,m.notes AS الملاحظات FROM stock_movements m JOIN products p ON p.id=m.product_id ORDER BY m.id DESC LIMIT 300""")); st.dataframe(df,use_container_width=True,hide_index=True)
    with tab3:
        cats=q("SELECT * FROM categories ORDER BY name"); cmap={x["name"]:x["id"] for x in cats}
        with st.form("new_product"):
            a,b,c=st.columns(3); sku=a.text_input("رمز الصنف"); name=b.text_input("اسم الصنف"); cat=c.selectbox("التصنيف",list(cmap) or ["غير مصنف"])
            d,e,f=st.columns(3); unit=d.text_input("الوحدة",value="قطعة"); cost=e.number_input("التكلفة",min_value=0.0); sale=f.number_input("سعر البيع",min_value=0.0)
            g,h=st.columns(2); opening=g.number_input("الرصيد الافتتاحي",min_value=0.0); minimum=h.number_input("الحد الأدنى",min_value=0.0)
            if st.form_submit_button("حفظ الصنف",type="primary"):
                try:
                    with get_db() as conn: pid=conn.execute("INSERT INTO products(sku,name,category_id,unit,cost_price,sale_price,stock_qty,min_stock,created_at) VALUES(?,?,?,?,?,?,?,?,?)",(sku,name,cmap.get(cat),unit,cost,sale,opening,minimum,now())).lastrowid
                    if opening: record_stock(pid,opening,"إدخال",cost,"رصيد افتتاحي")
                    st.success("تمت إضافة الصنف"); st.rerun()
                except sqlite3.IntegrityError: st.error("رمز الصنف مستخدم مسبقاً")

# العملاء والموردون
elif page=="العملاء والموردون":
    st.title("👥 العملاء والموردون")
    t1,t2=st.tabs(["قائمة الجهات","إضافة جهة"])
    with t1:
        df=pd.DataFrame(q("SELECT kind AS النوع,code AS الرمز,name AS الاسم,phone AS الهاتف,email AS البريد,address AS العنوان,opening_balance AS الرصيد_الافتتاحي FROM contacts WHERE active=1 ORDER BY id DESC")); st.dataframe(df,use_container_width=True,hide_index=True)
    with t2:
        with st.form("contact"):
            a,b,c=st.columns(3); kind=a.selectbox("النوع",["عميل","مورد"]); code=b.text_input("الرمز"); name=c.text_input("الاسم",required=True)
            d,e,f=st.columns(3); phone=d.text_input("الهاتف"); email=e.text_input("البريد"); opening=f.number_input("الرصيد الافتتاحي",min_value=0.0)
            address=st.text_area("العنوان")
            if st.form_submit_button("حفظ",type="primary"):
                try:q("INSERT INTO contacts(kind,code,name,phone,email,address,opening_balance,created_at) VALUES(?,?,?,?,?,?,?,?)",(kind,code or None,name,phone,email,address,opening,now()));st.success("تم حفظ الجهة");st.rerun()
                except sqlite3.IntegrityError:st.error("الرمز مستخدم مسبقاً")

# المصروفات
elif page=="المصروفات":
    st.title("💸 المصروفات")
    if not can("مدير النظام","محاسب"): st.warning("هذه الوحدة للمحاسبين والإدارة"); st.stop()
    with st.form("expense"):
        a,b,c=st.columns(3); title=a.text_input("البيان",required=True); category=b.text_input("التصنيف",value="تشغيلية"); amount=c.number_input("المبلغ",min_value=0.01)
        paid_from=st.selectbox("طريقة الدفع",["الصندوق","البنك"]); notes=st.text_area("ملاحظات")
        if st.form_submit_button("تسجيل المصروف",type="primary"):
            no=next_no("EXP"); eid=q("INSERT INTO expenses(expense_no,title,category,amount,paid_from,notes,created_at,user_id) VALUES(?,?,?,?,?,?,?,?)",(no,title,category,amount,paid_from,notes,now(),st.session_state.user_id)); post_journal(f"مصروف {title}",[{"account":"503","debit":amount},{"account":"101" if paid_from=="الصندوق" else "102","credit":amount}],no); audit("إنشاء","مصروف",None,no);st.success("تم تسجيل المصروف")
    st.dataframe(pd.DataFrame(q("SELECT expense_no AS الرقم,title AS البيان,category AS التصنيف,amount AS المبلغ,paid_from AS الدفع,created_at AS التاريخ FROM expenses ORDER BY id DESC")),use_container_width=True,hide_index=True)

# الموارد البشرية
elif page=="الموارد البشرية":
    st.title("👔 الموارد البشرية والرواتب")
    if not can("مدير النظام","مدير موارد بشرية"): st.warning("هذه الوحدة لمدير النظام والموارد البشرية"); st.stop()
    t1,t2=st.tabs(["الموظفون","الحضور والرواتب"])
    with t1:
        with st.form("employee"):
            a,b,c=st.columns(3); no=a.text_input("الرقم الوظيفي"); name=b.text_input("اسم الموظف",required=True); dept=c.selectbox("القسم",["الإدارة","المبيعات","المشتريات","المحاسبة","تقنية المعلومات"])
            d,e,f=st.columns(3); job=d.text_input("المسمى الوظيفي"); phone=e.text_input("الهاتف"); salary=f.number_input("الراتب الأساسي",min_value=0.0)
            if st.form_submit_button("إضافة موظف",type="primary"):
                try:q("INSERT INTO employees(employee_no,name,department,job_title,phone,basic_salary,hire_date) VALUES(?,?,?,?,?,?,?)",(no or next_no("EMP"),name,dept,job,phone,salary,date.today().isoformat()));st.success("تمت الإضافة");st.rerun()
                except sqlite3.IntegrityError:st.error("الرقم الوظيفي مستخدم")
        st.dataframe(pd.DataFrame(q("SELECT employee_no AS الرقم,name AS الموظف,department AS القسم,job_title AS المسمى,basic_salary AS الراتب,hire_date AS التعيين FROM employees WHERE active=1")),use_container_width=True,hide_index=True)
    with t2:
        emps=q("SELECT * FROM employees WHERE active=1"); emap={f"{x['employee_no']} - {x['name']}":x for x in emps}
        with st.form("attendance"):
            emp=st.selectbox("الموظف",list(emap) or ["لا يوجد"]); day=st.date_input("التاريخ",date.today()); status=st.selectbox("الحالة",["حاضر","غائب","إجازة","مهمة رسمية"]); note=st.text_input("ملاحظة")
            if st.form_submit_button("حفظ الحضور") and emap:
                q("INSERT OR REPLACE INTO attendance(employee_id,work_date,status,notes) VALUES(?,?,?,?)",(emap[emp]["id"],str(day),status,note));st.success("تم حفظ الحضور")
        st.dataframe(pd.DataFrame(q("SELECT a.work_date AS التاريخ,e.name AS الموظف,a.status AS الحالة,a.notes AS ملاحظة FROM attendance a JOIN employees e ON e.id=a.employee_id ORDER BY a.id DESC LIMIT 100")),use_container_width=True,hide_index=True)

# المحاسبة
elif page=="المحاسبة":
    st.title("📚 المحاسبة والقيود اليومية")
    if not can("مدير النظام","محاسب"): st.warning("هذه الوحدة للمحاسبين والإدارة"); st.stop()
    t1,t2,t3=st.tabs(["قيد يدوي","دليل الحسابات","دفتر اليومية"])
    accounts=q("SELECT * FROM accounts WHERE active=1 ORDER BY code"); amap={f"{x['code']} - {x['name']}":x['code'] for x in accounts}
    with t1:
        with st.form("manual_journal"):
            desc=st.text_input("بيان القيد",required=True); ref=st.text_input("المرجع"); debit_acc=st.selectbox("الحساب المدين",list(amap)); credit_acc=st.selectbox("الحساب الدائن",list(amap)); amount=st.number_input("المبلغ",min_value=0.01); currency=st.selectbox("العملة",[x["code"] for x in q("SELECT * FROM currencies WHERE active=1")]); rate=st.number_input("سعر الصرف",min_value=0.000001,value=1.0)
            if st.form_submit_button("ترحيل القيد",type="primary"):
                ok,msg=post_journal(desc,[{"account":amap[debit_acc],"debit":amount*rate,"currency":currency,"foreign_amount":amount,"rate":rate},{"account":amap[credit_acc],"credit":amount*rate,"currency":currency,"foreign_amount":amount,"rate":rate}],ref); st.success("تم الترحيل "+str(msg)) if ok else st.error(msg)
    with t2: st.dataframe(pd.DataFrame(q("SELECT code AS الرقم,name AS الحساب,account_type AS النوع,parent_code AS الحساب_الأب FROM accounts ORDER BY code")),use_container_width=True,hide_index=True)
    with t3: st.dataframe(pd.DataFrame(q("""SELECT e.entry_no AS الرقم,e.entry_date AS التاريخ,e.description AS البيان,l.account_code AS الحساب,l.debit AS مدين,l.credit AS دائن,l.currency_code AS العملة FROM journal_entries e JOIN journal_lines l ON l.entry_id=e.id ORDER BY e.id DESC LIMIT 300""")),use_container_width=True,hide_index=True)

# التقارير
elif page=="التقارير":
    st.title("📈 التقارير الإدارية والمالية")
    if not can("مدير النظام","محاسب","مراقب مخزون"): st.warning("لا تملك الصلاحية"); st.stop()
    report=st.selectbox("نوع التقرير",["ميزان المراجعة","قائمة الدخل","حركة المخزون","حركة المبيعات","سجل التدقيق"])
    if report=="ميزان المراجعة":
        df=pd.DataFrame(q("""SELECT a.code AS الحساب,a.name AS البيان,a.account_type AS النوع,COALESCE(SUM(l.debit),0) AS مدين,COALESCE(SUM(l.credit),0) AS دائن,COALESCE(SUM(l.debit),0)-COALESCE(SUM(l.credit),0) AS الرصيد FROM accounts a LEFT JOIN journal_lines l ON a.code=l.account_code GROUP BY a.code ORDER BY a.code"""));st.dataframe(df,use_container_width=True,hide_index=True)
    elif report=="قائمة الدخل":
        df=pd.DataFrame(q("""SELECT a.name AS البند,a.account_type AS النوع,SUM(l.credit)-SUM(l.debit) AS القيمة FROM accounts a JOIN journal_lines l ON a.code=l.account_code WHERE a.account_type IN ('إيرادات','مصروفات') GROUP BY a.code"""));st.dataframe(df,use_container_width=True,hide_index=True)
    elif report=="حركة المخزون":st.dataframe(pd.DataFrame(q("SELECT p.name AS الصنف,m.movement_type AS الحركة,m.quantity AS الكمية,m.unit_cost AS التكلفة,m.reference AS المرجع,m.created_at AS التاريخ FROM stock_movements m JOIN products p ON p.id=m.product_id ORDER BY m.id DESC")),use_container_width=True,hide_index=True)
    elif report=="حركة المبيعات":st.dataframe(pd.DataFrame(q("SELECT invoice_no AS الفاتورة,total AS الإجمالي,status AS الحالة,created_at AS التاريخ FROM invoices WHERE invoice_type='بيع' ORDER BY id DESC")),use_container_width=True,hide_index=True)
    else:st.dataframe(pd.DataFrame(q("SELECT created_at AS التاريخ,action AS الإجراء,entity AS الكيان,entity_id AS الرقم,details AS التفاصيل FROM audit_log ORDER BY id DESC LIMIT 500")),use_container_width=True,hide_index=True)

# الإعدادات
elif page=="الإعدادات":
    st.title("⚙️ الإعدادات وإدارة النظام")
    if not can("مدير النظام"): st.warning("هذه الوحدة لمدير النظام فقط"); st.stop()
    t1,t2,t3=st.tabs(["المستخدمون","العملات","التصنيفات"])
    with t1:
        with st.form("new_user"):
            a,b,c=st.columns(3); username=a.text_input("اسم المستخدم"); fullname=b.text_input("الاسم الكامل"); role=c.selectbox("الصلاحية",ROLES); password=st.text_input("كلمة المرور",type="password")
            if st.form_submit_button("إضافة مستخدم"):
                try:q("INSERT INTO users(username,password_hash,full_name,role,created_at) VALUES(?,?,?,?,?)",(username,hash_password(password),fullname,role,now()));st.success("تمت الإضافة")
                except sqlite3.IntegrityError:st.error("اسم المستخدم موجود")
        st.dataframe(pd.DataFrame(q("SELECT username AS المستخدم,full_name AS الاسم,role AS الصلاحية,active AS فعال,created_at AS الإنشاء FROM users")),use_container_width=True,hide_index=True)
    with t2:
        with st.form("currency"):
            code=st.text_input("الرمز"); name=st.text_input("اسم العملة"); symbol=st.text_input("الرمز المختصر"); rate=st.number_input("سعر الصرف مقابل العملة الأساسية",min_value=0.000001,value=1.0)
            if st.form_submit_button("حفظ العملة"):q("INSERT OR REPLACE INTO currencies(code,name,symbol,exchange_rate) VALUES(?,?,?,?)",(code.upper(),name,symbol,rate));st.success("تم الحفظ")
        st.dataframe(pd.DataFrame(q("SELECT code AS الرمز,name AS العملة,symbol AS الاختصار,exchange_rate AS سعر_الصرف FROM currencies")),use_container_width=True,hide_index=True)
    with t3:
        name=st.text_input("اسم التصنيف الجديد")
        if st.button("إضافة التصنيف") and name:
            try:q("INSERT INTO categories(name) VALUES(?)",(name,));st.success("تمت الإضافة");st.rerun()
            except sqlite3.IntegrityError:st.error("التصنيف موجود مسبقاً")
        st.dataframe(pd.DataFrame(q("SELECT id AS الرقم,name AS التصنيف FROM categories")),use_container_width=True,hide_index=True)
