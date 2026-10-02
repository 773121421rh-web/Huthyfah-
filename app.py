import streamlit as st
import sqlite3
import pandas as pd
import re
from datetime import datetime

# ==========================================
# 1. تهيئة قاعدة البيانات الشاملة (ERP Database)
# ==========================================
def init_db():
    conn = sqlite3.connect("super_erp_system.db")
    c = conn.cursor()
    c.executescript('''
        CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY, username TEXT UNIQUE, password TEXT, role TEXT);
        CREATE TABLE IF NOT EXISTS currencies (code TEXT PRIMARY KEY, name TEXT, exchange_rate REAL);
        CREATE TABLE IF NOT EXISTS items (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, cost_price REAL, sale_price REAL, stock_qty REAL);
        CREATE TABLE IF NOT EXISTS employees (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, department TEXT, basic_salary REAL);
        CREATE TABLE IF NOT EXISTS accounts (code TEXT PRIMARY KEY, name TEXT, type TEXT);
        CREATE TABLE IF NOT EXISTS journal_entries (id INTEGER PRIMARY KEY AUTOINCREMENT, date TEXT, description TEXT, user_id INTEGER);
        CREATE TABLE IF NOT EXISTS journal_lines (
            id INTEGER PRIMARY KEY AUTOINCREMENT, entry_id INTEGER, 
            account_code TEXT, currency_code TEXT, foreign_amount REAL, 
            exchange_rate REAL, debit REAL, credit REAL
        );
    ''')
    
    # إدراج البيانات الافتراضية إذا كانت قاعدة البيانات فارغة
    c.execute("SELECT COUNT(*) FROM users")
    if c.fetchone()[0] == 0:
        # المستخدم الافتراضي
        c.execute("INSERT INTO users (username, password, role) VALUES ('admin', 'admin', 'مدير النظام')")
        
        # العملات
        c.executemany("INSERT INTO currencies VALUES (?,?,?)", [("SAR", "ريال سعودي (الأساسية)", 1.0), ("USD", "دولار أمريكي", 3.75)])
        
        # الأصناف الافتراضية
        c.executemany("INSERT INTO items (name, cost_price, sale_price, stock_qty) VALUES (?,?,?,?)", [
            ("لابتوب ديل", 1500, 2500, 50),
            ("طابعة إتش بي", 500, 800, 100)
        ])
        
        # الدليل المحاسبي
        accounts = [
            ("101", "النقدية بالصندوق", "أصول"), ("102", "البنك", "أصول"),
            ("103", "المخزون", "أصول"), ("104", "العملاء", "أصول"),
            ("201", "الموردون", "خصوم"), ("301", "رأس المال", "حقوق ملكية"),
            ("401", "إيرادات المبيعات", "إيرادات"), ("501", "تكلفة المبيعات", "مصروفات"),
            ("502", "مصروفات الرواتب", "مصروفات"), ("503", "فروق العملات", "مصروفات")
        ]
        c.executemany("INSERT INTO accounts VALUES (?,?,?)", accounts)
    conn.commit()
    return conn

# ==========================================
# 2. محرك الترحيل المحاسبي (بما يشمل العملات)
# ==========================================
def post_entry(conn, description, lines, user_id=1):
    total_debit = sum(l.get('debit', 0) for l in lines)
    total_credit = sum(l.get('credit', 0) for l in lines)
    
    if round(total_debit, 2) != round(total_credit, 2):
        return False, f"القيد غير متزن! المدين: {total_debit}، الدائن: {total_credit}"
    
    c = conn.cursor()
    date = datetime.now().strftime("%Y-%m-%d %H:%M")
    c.execute("INSERT INTO journal_entries (date, description, user_id) VALUES (?,?,?)", (date, description, user_id))
    entry_id = c.lastrowid
    
    for l in lines:
        curr = l.get('currency', 'SAR')
        rate = l.get('rate', 1.0)
        fc_amt = l.get('foreign_amount', 0.0)
        c.execute("""INSERT INTO journal_lines (entry_id, account_code, currency_code, foreign_amount, exchange_rate, debit, credit) 
                     VALUES (?,?,?,?,?,?,?)""", 
                  (entry_id, l['acc'], curr, fc_amt, rate, l['debit'], l['credit']))
    conn.commit()
    return True, entry_id

# ==========================================
# 3. نظام تسجيل الدخول (Authentication)
# ==========================================
st.set_page_config(page_title="Ultra ERP System", layout="wide")
conn = init_db()

if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
    st.session_state.username = ""
    st.session_state.role = ""

if not st.session_state.logged_in:
    st.title("🔐 تسجيل الدخول للنظام")
    st.info("اسم المستخدم الافتراضي: **admin** | كلمة المرور: **admin**")
    user = st.text_input("اسم المستخدم")
    pwd = st.text_input("كلمة المرور", type="password")
    if st.button("دخول"):
        c = conn.cursor()
        c.execute("SELECT id, role FROM users WHERE username=? AND password=?", (user, pwd))
        res = c.fetchone()
        if res:
            st.session_state.logged_in = True
            st.session_state.user_id = res[0]
            st.session_state.username = user
            st.session_state.role = res[1]
            st.rerun()
        else:
            st.error("بيانات الدخول غير صحيحة.")
    st.stop()

# ==========================================
# 4. واجهة النظام الرئيسية (Dashboard)
# ==========================================
st.sidebar.title(f"مرحباً، {st.session_state.username}")
st.sidebar.write(f"الصلاحية: {st.session_state.role}")
if st.sidebar.button("تسجيل الخروج"):
    st.session_state.logged_in = False
    st.rerun()

st.title("🌐 نظام إدارة الموارد المتكامل (ERP)")

tab_trade, tab_inventory, tab_hr, tab_finance, tab_reports, tab_settings = st.tabs([
    "🛒 المبيعات والمشتريات", "📦 المخزون", "👥 شؤون الموظفين", 
    "💱 الحسابات والعملات", "📊 التقارير", "⚙️ الإعدادات"
])

# --- 1. المبيعات والمشتريات (تحديث آلي للمخزون) ---
with tab_trade:
    items_df = pd.read_sql_query("SELECT id, name, cost_price, sale_price, stock_qty FROM items", conn)
    item_dict = {f"{row['id']} - {row['name']} (متاح: {row['stock_qty']})": row for _, row in items_df.iterrows()}
    
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("### 💰 شاشة المبيعات")
        sel_item_sale = st.selectbox("اختر الصنف للبيع:", list(item_dict.keys()), key="sale_item")
        sale_qty = st.number_input("الكمية المباعة:", min_value=1, value=1, key="sale_qty")
        if st.button("تنفيذ البيع (نقداً)"):
            item_data = item_dict[sel_item_sale]
            if sale_qty <= item_data['stock_qty']:
                total_sale = sale_qty * item_data['sale_price']
                total_cost = sale_qty * item_data['cost_price']
                
                # 1. تحديث المخزون
                c = conn.cursor()
                c.execute("UPDATE items SET stock_qty = stock_qty - ? WHERE id = ?", (sale_qty, item_data['id']))
                
                # 2. توليد القيد المحاسبي المزدوج
                lines = [
                    {"acc": "101", "debit": total_sale, "credit": 0},         # النقدية المستلمة
                    {"acc": "401", "debit": 0, "credit": total_sale},         # إيراد مبيعات
                    {"acc": "501", "debit": total_cost, "credit": 0},         # تكلفة البضاعة
                    {"acc": "103", "debit": 0, "credit": total_cost}          # خفض المخزون
                ]
                post_entry(conn, f"بيع {sale_qty} من {item_data['name']}", lines, st.session_state.user_id)
                st.success(f"تم البيع بنجاح! الإجمالي: {total_sale}")
            else:
                st.error("الكمية المطلوبة غير متوفرة في المخزون!")

    with col2:
        st.markdown("### 🛒 شاشة المشتريات")
        sel_item_pur = st.selectbox("اختر الصنف للشراء:", list(item_dict.keys()), key="pur_item")
        pur_qty = st.number_input("الكمية المشتراة:", min_value=1, value=1, key="pur_qty")
        if st.button("تنفيذ الشراء (نقداً)"):
            item_data = item_dict[sel_item_pur]
            total_cost = pur_qty * item_data['cost_price']
            
            c = conn.cursor()
            c.execute("UPDATE items SET stock_qty = stock_qty + ? WHERE id = ?", (pur_qty, item_data['id']))
            lines = [
                {"acc": "103", "debit": total_cost, "credit": 0},
                {"acc": "101", "debit": 0, "credit": total_cost}
            ]
            post_entry(conn, f"شراء {pur_qty} من {item_data['name']}", lines, st.session_state.user_id)
            st.success(f"تم الشراء وإضافة الكمية للمخزون. الإجمالي: {total_cost}")

# --- 2. المخزون والأصناف ---
with tab_inventory:
    st.markdown("### 📦 تقرير المخزون اللحظي")
    st.dataframe(items_df[['id', 'name', 'cost_price', 'sale_price', 'stock_qty']].rename(columns={
        'id':'رقم الصنف', 'name':'الاسم', 'cost_price':'التكلفة', 'sale_price':'سعر البيع', 'stock_qty':'الرصيد'
    }), use_container_width=True)

# --- 3. شؤون الموظفين (HR) ---
with tab_hr:
    col_hr1, col_hr2 = st.columns(2)
    with col_hr1:
        st.markdown("### ➕ إضافة موظف جديد")
        emp_name = st.text_input("اسم الموظف:")
        emp_dept = st.selectbox("القسم:", ["الإدارة", "المبيعات", "المشتريات", "تقنية المعلومات"])
        emp_salary = st.number_input("الراتب الأساسي:", min_value=1000.0)
        if st.button("حفظ الموظف"):
            c = conn.cursor()
            c.execute("INSERT INTO employees (name, department, basic_salary) VALUES (?,?,?)", (emp_name, emp_dept, emp_salary))
            conn.commit()
            st.success("تم إضافة الموظف.")
            
    with col_hr2:
        st.markdown("### 💸 مسير الرواتب")
        df_emps = pd.read_sql_query("SELECT * FROM employees", conn)
        st.dataframe(df_emps[['name', 'department', 'basic_salary']])
        total_salaries = df_emps['basic_salary'].sum() if not df_emps.empty else 0
        
        if st.button(f"صرف رواتب الجميع ({total_salaries}) من البنك"):
            if total_salaries > 0:
                lines = [{"acc": "502", "debit": total_salaries, "credit": 0}, {"acc": "102", "debit": 0, "credit": total_salaries}]
                post_entry(conn, "صرف رواتب الموظفين لشهر الحالي", lines, st.session_state.user_id)
                st.success("تم صرف الرواتب وتوليد القيد.")

# --- 4. الحسابات والعملات (Multi-Currency GL) ---
with tab_finance:
    st.markdown("### 💱 قيد يومية متعدد العملات")
    curr_df = pd.read_sql_query("SELECT code, exchange_rate FROM currencies", conn)
    curr_dict = dict(zip(curr_df['code'], curr_df['exchange_rate']))
    
    sel_curr = st.selectbox("عملة القيد:", list(curr_dict.keys()))
    exch_rate = curr_dict[sel_curr]
    st.info(f"سعر الصرف الحالي للعملة المختارة مقابل الأساسية: {exch_rate}")
    
    amount_fc = st.number_input("المبلغ (بالعملة المختارة):", min_value=0.0)
    amount_local = round(amount_fc * exch_rate, 2)
    st.write(f"**المعادل بالعملة المحلية:** {amount_local}")
    
    acc_df = pd.read_sql_query("SELECT code, name FROM accounts", conn)
    acc_list = acc_df['code'].astype(str) + " - " + acc_df['name']
    
    acc_debit = st.selectbox("الحساب المدين:", acc_list)
    acc_credit = st.selectbox("الحساب الدائن:", acc_list)
    desc_entry = st.text_input("بيان القيد:")
    
    if st.button("ترحيل القيد"):
        if amount_local > 0:
            lines = [
                {"acc": acc_debit.split(" - ")[0], "debit": amount_local, "credit": 0, "currency": sel_curr, "rate": exch_rate, "foreign_amount": amount_fc},
                {"acc": acc_credit.split(" - ")[0], "debit": 0, "credit": amount_local, "currency": sel_curr, "rate": exch_rate, "foreign_amount": amount_fc}
            ]
            success, msg = post_entry(conn, desc_entry, lines, st.session_state.user_id)
            if success: st.success("تم الترحيل بنجاح.")
            else: st.error(msg)

# --- 5. التقارير الشاملة ---
with tab_reports:
    rep = st.radio("اختر التقرير:", ["ميزان المراجعة", "قائمة الدخل", "حركة دفتر اليومية"], horizontal=True)
    if rep == "ميزان المراجعة":
        df_tb = pd.read_sql_query("""
            SELECT a.code AS رقم, a.name AS الحساب, a.type AS التصنيف, 
                   SUM(l.debit) AS مدين, SUM(l.credit) AS دائن, (SUM(l.debit) - SUM(l.credit)) AS الرصيد 
            FROM accounts a LEFT JOIN journal_lines l ON a.code = l.account_code 
            GROUP BY a.code HAVING الرصيد != 0 OR مدين > 0
        """, conn)
        st.dataframe(df_tb, use_container_width=True)
    elif rep == "حركة دفتر اليومية":
        df_jl = pd.read_sql_query("""
            SELECT e.date AS التاريخ, e.description AS البيان, a.name AS الحساب, 
                   l.currency_code AS العملة, l.foreign_amount AS مبلغ_أجنبي, l.debit AS مدين_محلي, l.credit AS دائن_محلي, u.username AS المستخدم
            FROM journal_entries e 
            JOIN journal_lines l ON e.id = l.entry_id 
            JOIN accounts a ON l.account_code = a.code
            JOIN users u ON e.user_id = u.id
            ORDER BY e.id DESC
        """, conn)
        st.dataframe(df_jl, use_container_width=True)
    elif rep == "قائمة الدخل":
        query_pl = "SELECT a.name AS البند, a.type AS النوع, SUM(l.credit) - SUM(l.debit) AS القيمة FROM accounts a JOIN journal_lines l ON a.code = l.account_code WHERE a.type IN ('إيرادات', 'مصروفات') GROUP BY a.code"
        df_pl = pd.read_sql_query(query_pl, conn)
        if not df_pl.empty:
            df_pl.loc[df_pl['النوع'] == 'مصروفات', 'القيمة'] = df_pl['القيمة'] * -1
            st.table(df_pl[['البند', 'القيمة']])
            net_income = df_pl[df_pl['النوع'] == 'إيرادات']['القيمة'].sum() - df_pl[df_pl['النوع'] == 'مصروفات']['القيمة'].sum()
            st.metric(label="صافي الربح / (الخسارة)", value=f"{net_income:,.2f}")

# --- 6. الإعدادات (تعريف المستخدمين والأصناف والعملات) ---
with tab_settings:
    st.markdown("### ⚙️ إعدادات النظام المتقدمة")
    if st.session_state.role != "مدير النظام":
        st.warning("هذه الشاشة مخصصة لمدير النظام فقط.")
    else:
        set_sel = st.selectbox("اختر ما تود إعداده:", ["إضافة مستخدم جديد", "إضافة صنف جديد", "تحديث أسعار الصرف"])
        if set_sel == "إضافة مستخدم جديد":
            new_u = st.text_input("اسم المستخدم الجديد:")
            new_p = st.text_input("كلمة المرور:", type="password")
            new_r = st.selectbox("الصلاحية:", ["مدير النظام", "محاسب", "موظف مبيعات"])
            if st.button("حفظ المستخدم"):
                try:
                    conn.execute("INSERT INTO users (username, password, role) VALUES (?,?,?)", (new_u, new_p, new_r))
                    conn.commit()
                    st.success("تم إضافة المستخدم.")
                except:
                    st.error("اسم المستخدم موجود مسبقاً.")
        
        elif set_sel == "إضافة صنف جديد":
            item_n = st.text_input("اسم الصنف:")
            item_c = st.number_input("التكلفة الافتراضية:", min_value=0.0)
            item_p = st.number_input("سعر البيع:", min_value=0.0)
            if st.button("حفظ الصنف"):
                conn.execute("INSERT INTO items (name, cost_price, sale_price, stock_qty) VALUES (?,?,?,0)", (item_n, item_c, item_p))
                conn.commit()
                st.success("تم إضافة الصنف لقاعدة البيانات.")
                
        elif set_sel == "تحديث أسعار الصرف":
            df_cur = pd.read_sql_query("SELECT * FROM currencies", conn)
            st.write("أسعار الصرف الحالية:")
            st.table(df_cur)
            new_c_code = st.text_input("رمز العملة (مثال: EUR):")
            new_c_name = st.text_input("اسم العملة (مثال: يورو):")
            new_c_rate = st.number_input("سعر الصرف مقابل الأساسية:", min_value=0.01)
            if st.button("حفظ/تحديث العملة"):
                conn.execute("INSERT OR REPLACE INTO currencies (code, name, exchange_rate) VALUES (?,?,?)", (new_c_code, new_c_name, new_c_rate))
                conn.commit()
                st.success("تم تحديث جدول العملات.")
