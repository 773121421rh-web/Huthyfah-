import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime

# ==========================================
# 1. تهيئة قاعدة البيانات (مع العملة الجديدة)
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
    
    c.execute("SELECT COUNT(*) FROM users")
    if c.fetchone()[0] == 0:
        c.execute("INSERT INTO users (username, password, role) VALUES ('admin', 'admin', 'مدير النظام')")
        
        # إضافة الريال اليمني (مع افتراض أن الريال السعودي هو الأساس 1.0)
        c.executemany("INSERT INTO currencies VALUES (?,?,?)", [
            ("SAR", "ريال سعودي (الأساسية)", 1.0), 
            ("USD", "دولار أمريكي", 3.75),
            ("YER", "ريال يمني", 0.0071)
        ])
        
        c.executemany("INSERT INTO items (name, cost_price, sale_price, stock_qty) VALUES (?,?,?,?)", [
            ("لابتوب ديل", 1500, 2500, 50),
            ("طابعة إتش بي", 500, 800, 100)
        ])
        
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
# 2. محرك الترحيل المحاسبي
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
# 3. تسجيل الدخول (Authentication)
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
# 4. واجهة النظام وتوزيع الصلاحيات (RBAC)
# ==========================================
st.sidebar.title(f"مرحباً، {st.session_state.username}")
st.sidebar.write(f"الصلاحية: **{st.session_state.role}**")
if st.sidebar.button("تسجيل الخروج"):
    st.session_state.logged_in = False
    st.rerun()

st.title("🌐 نظام إدارة الموارد المتكامل (ERP)")
role = st.session_state.role

tab_trade, tab_inventory, tab_hr, tab_finance, tab_reports, tab_settings = st.tabs([
    "🛒 المبيعات والمشتريات", "📦 المخزون", "👥 شؤون الموظفين", 
    "💱 الحسابات والعملات", "📊 التقارير", "⚙️ الإعدادات"
])

# --- 1. المبيعات والمشتريات ---
with tab_trade:
    if role in ["مدير النظام", "موظف مبيعات", "محاسب"]:
        items_df = pd.read_sql_query("SELECT id, name, cost_price, sale_price, stock_qty FROM items", conn)
        item_dict = {f"{row['id']} - {row['name']} (متاح: {row['stock_qty']})": row for _, row in items_df.iterrows()}
        
        col1, col2 = st.columns(2)
        with col1:
            st.markdown("### 💰 شاشة المبيعات")
            if item_dict:
                sel_item_sale = st.selectbox("اختر الصنف للبيع:", list(item_dict.keys()), key="sale_item")
                sale_qty = st.number_input("الكمية المباعة:", min_value=1, value=1, key="sale_qty")
                if st.button("تنفيذ البيع (نقداً)"):
                    item_data = item_dict[sel_item_sale]
                    if sale_qty <= item_data['stock_qty']:
                        t_sale, t_cost = sale_qty * item_data['sale_price'], sale_qty * item_data['cost_price']
                        c = conn.cursor()
                        c.execute("UPDATE items SET stock_qty = stock_qty - ? WHERE id = ?", (sale_qty, item_data['id']))
                        lines = [
                            {"acc": "101", "debit": t_sale, "credit": 0}, {"acc": "401", "debit": 0, "credit": t_sale},
                            {"acc": "501", "debit": t_cost, "credit": 0}, {"acc": "103", "debit": 0, "credit": t_cost}
                        ]
                        post_entry(conn, f"بيع {sale_qty} من {item_data['name']}", lines, st.session_state.user_id)
                        st.success(f"تم البيع! الإجمالي: {t_sale}")
                        st.rerun()
                    else: st.error("الكمية المطلوبة غير متوفرة!")
            else: st.info("لا توجد أصناف.")

        with col2:
            st.markdown("### 🛒 شاشة المشتريات")
            if item_dict:
                sel_item_pur = st.selectbox("اختر الصنف للشراء:", list(item_dict.keys()), key="pur_item")
                pur_qty = st.number_input("الكمية المشتراة:", min_value=1, value=1, key="pur_qty")
                if st.button("تنفيذ الشراء (نقداً)"):
                    item_data = item_dict[sel_item_pur]
                    t_cost = pur_qty * item_data['cost_price']
                    c = conn.cursor()
                    c.execute("UPDATE items SET stock_qty = stock_qty + ? WHERE id = ?", (pur_qty, item_data['id']))
                    lines = [{"acc": "103", "debit": t_cost, "credit": 0}, {"acc": "101", "debit": 0, "credit": t_cost}]
                    post_entry(conn, f"شراء {pur_qty} من {item_data['name']}", lines, st.session_state.user_id)
                    st.success(f"تم الشراء! الإجمالي: {t_cost}")
                    st.rerun()
    else:
        st.warning("ليس لديك صلاحية للوصول إلى قسم المبيعات والمشتريات.")

# --- 2. المخزون ---
with tab_inventory:
    if role in ["مدير النظام", "محاسب", "موظف مبيعات"]:
        st.markdown("### 📦 تقرير المخزون اللحظي")
        st.dataframe(pd.read_sql_query("SELECT id AS رقم_الصنف, name AS الاسم, cost_price AS التكلفة, sale_price AS سعر_البيع, stock_qty AS الرصيد FROM items", conn), use_container_width=True)
    else:
        st.warning("ليس لديك صلاحية لعرض المخزون.")

# --- 3. شؤون الموظفين (إضافة وتعديل) ---
with tab_hr:
    if role in ["مدير النظام", "مدير موارد بشرية"]:
        col_hr1, col_hr2 = st.columns(2)
        with col_hr1:
            st.markdown("### ✏️ إدارة الموظفين")
            emp_action = st.radio("اختر الإجراء:", ["إضافة موظف جديد", "تعديل/حذف موظف حالي"], horizontal=True)
            
            if emp_action == "إضافة موظف جديد":
                emp_name = st.text_input("اسم الموظف:")
                emp_dept = st.selectbox("القسم:", ["الإدارة", "المبيعات", "المشتريات", "تقنية المعلومات"])
                emp_salary = st.number_input("الراتب الأساسي:", min_value=1000.0)
                if st.button("حفظ الموظف"):
                    conn.execute("INSERT INTO employees (name, department, basic_salary) VALUES (?,?,?)", (emp_name, emp_dept, emp_salary))
                    conn.commit()
                    st.success("تم إضافة الموظف بنجاح.")
                    st.rerun()
            else:
                df_emps = pd.read_sql_query("SELECT * FROM employees", conn)
                if not df_emps.empty:
                    emp_dict = {row['id']: f"{row['name']} - {row['department']}" for _, row in df_emps.iterrows()}
                    sel_emp_id = st.selectbox("اختر الموظف:", list(emp_dict.keys()), format_func=lambda x: emp_dict[x])
                    sel_emp_data = df_emps[df_emps['id'] == sel_emp_id].iloc[0]
                    
                    new_dept = st.selectbox("تعديل القسم:", ["الإدارة", "المبيعات", "المشتريات", "تقنية المعلومات"], index=["الإدارة", "المبيعات", "المشتريات", "تقنية المعلومات"].index(sel_emp_data['department']))
                    new_salary = st.number_input("تعديل الراتب الأساسي:", min_value=0.0, value=float(sel_emp_data['basic_salary']))
                    
                    c1, c2 = st.columns(2)
                    if c1.button("تحديث بيانات الموظف"):
                        conn.execute("UPDATE employees SET department=?, basic_salary=? WHERE id=?", (new_dept, new_salary, sel_emp_id))
                        conn.commit()
                        st.success("تم التحديث.")
                        st.rerun()
                    if c2.button("حذف الموظف"):
                        conn.execute("DELETE FROM employees WHERE id=?", (sel_emp_id,))
                        conn.commit()
                        st.success("تم الحذف.")
                        st.rerun()
                else: st.info("لا يوجد موظفين حالياً.")
                
        with col_hr2:
            st.markdown("### 💸 مسير الرواتب")
            df_emps_display = pd.read_sql_query("SELECT name AS الموظف, department AS القسم, basic_salary AS الراتب FROM employees", conn)
            st.dataframe(df_emps_display)
            total_salaries = df_emps_display['الراتب'].sum() if not df_emps_display.empty else 0
            
            if st.button(f"صرف رواتب الجميع ({total_salaries}) من البنك") and total_salaries > 0:
                lines = [{"acc": "502", "debit": total_salaries, "credit": 0}, {"acc": "102", "debit": 0, "credit": total_salaries}]
                post_entry(conn, "صرف رواتب الموظفين", lines, st.session_state.user_id)
                st.success("تم صرف الرواتب وتوليد القيد.")
    else:
        st.warning("هذا القسم مخصص لمدير النظام أو مدير الموارد البشرية فقط.")

# --- 4. الحسابات والعملات ---
with tab_finance:
    if role in ["مدير النظام", "محاسب"]:
        st.markdown("### 💱 قيد يومية متعدد العملات")
        curr_df = pd.read_sql_query("SELECT code, name, exchange_rate FROM currencies", conn)
        curr_dict = {row['code']: row['exchange_rate'] for _, row in curr_df.iterrows()}
        
        sel_curr = st.selectbox("عملة القيد:", list(curr_dict.keys()), format_func=lambda x: f"{x} - {curr_df[curr_df['code']==x]['name'].values[0]}")
        exch_rate = curr_dict[sel_curr]
        st.info(f"سعر الصرف الحالي للعملة مقابل الأساسية: {exch_rate}")
        
        amount_fc = st.number_input("المبلغ (بالعملة المختارة):", min_value=0.0)
        amount_local = round(amount_fc * exch_rate, 2)
        st.write(f"**المعادل بالعملة المحلية للترحيل:** {amount_local}")
        
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
    else:
        st.warning("هذا القسم مخصص للإدارة المالية والمحاسبين فقط.")

# --- 5. التقارير ---
with tab_reports:
    if role in ["مدير النظام", "محاسب"]:
        rep = st.radio("اختر التقرير:", ["ميزان المراجعة", "قائمة الدخل", "حركة دفتر اليومية"], horizontal=True)
        if rep == "ميزان المراجعة":
            st.dataframe(pd.read_sql_query("""
                SELECT a.code AS رقم, a.name AS الحساب, a.type AS التصنيف, SUM(l.debit) AS مدين, SUM(l.credit) AS دائن, (SUM(l.debit) - SUM(l.credit)) AS الرصيد 
                FROM accounts a LEFT JOIN journal_lines l ON a.code = l.account_code GROUP BY a.code HAVING الرصيد != 0 OR مدين > 0
            """, conn), use_container_width=True)
        elif rep == "حركة دفتر اليومية":
            st.dataframe(pd.read_sql_query("""
                SELECT e.date AS التاريخ, e.description AS البيان, a.name AS الحساب, l.currency_code AS العملة, l.foreign_amount AS مبلغ_أجنبي, l.debit AS مدين_محلي, l.credit AS دائن_محلي, u.username AS المستخدم
                FROM journal_entries e JOIN journal_lines l ON e.id = l.entry_id JOIN accounts a ON l.account_code = a.code JOIN users u ON e.user_id = u.id ORDER BY e.id DESC
            """, conn), use_container_width=True)
        elif rep == "قائمة الدخل":
            df_pl = pd.read_sql_query("SELECT a.name AS البند, a.type AS النوع, SUM(l.credit) - SUM(l.debit) AS القيمة FROM accounts a JOIN journal_lines l ON a.code = l.account_code WHERE a.type IN ('إيرادات', 'مصروفات') GROUP BY a.code", conn)
            if not df_pl.empty:
                df_pl.loc[df_pl['النوع'] == 'مصروفات', 'القيمة'] *= -1
                st.table(df_pl[['البند', 'القيمة']])
                st.metric(label="صافي الربح / (الخسارة)", value=f"{df_pl[df_pl['النوع'] == 'إيرادات']['القيمة'].sum() - df_pl[df_pl['النوع'] == 'مصروفات']['القيمة'].sum():,.2f}")
    else:
        st.warning("التقارير المالية مخصصة للإدارة والمحاسبين فقط.")

# --- 6. الإعدادات وإدارة المستخدمين ---
with tab_settings:
    st.markdown("### ⚙️ إعدادات النظام المتقدمة")
    if role != "مدير النظام":
        st.warning("هذه الشاشة مخصصة لمدير النظام فقط.")
    else:
        set_sel = st.selectbox("اختر ما تود إعداده:", ["إدارة المستخدمين والصلاحيات", "إضافة صنف جديد", "تحديث أسعار الصرف"])
        
        if set_sel == "إدارة المستخدمين والصلاحيات":
            u_action = st.radio("الإجراء:", ["إضافة مستخدم", "تعديل/حذف مستخدم"], horizontal=True)
            if u_action == "إضافة مستخدم":
                new_u = st.text_input("اسم المستخدم الجديد:")
                new_p = st.text_input("كلمة المرور:", type="password")
                new_r = st.selectbox("الصلاحية:", ["مدير النظام", "محاسب", "موظف مبيعات", "مدير موارد بشرية"])
                if st.button("حفظ المستخدم"):
                    try:
                        conn.execute("INSERT INTO users (username, password, role) VALUES (?,?,?)", (new_u, new_p, new_r))
                        conn.commit()
                        st.success("تم إضافة المستخدم.")
                    except: st.error("اسم المستخدم موجود مسبقاً.")
            else:
                users_df = pd.read_sql_query("SELECT id, username, role FROM users", conn)
                u_dict = {row['id']: f"{row['username']} ({row['role']})" for _, row in users_df.iterrows()}
                sel_u_id = st.selectbox("اختر المستخدم:", list(u_dict.keys()), format_func=lambda x: u_dict[x])
                new_role = st.selectbox("تغيير الصلاحية:", ["مدير النظام", "محاسب", "موظف مبيعات", "مدير موارد بشرية"])
                new_pass = st.text_input("تعيين كلمة مرور جديدة (اتركه فارغاً لعدم التغيير):", type="password")
                
                uc1, uc2 = st.columns(2)
                if uc1.button("تحديث المستخدم"):
                    if new_pass: conn.execute("UPDATE users SET role=?, password=? WHERE id=?", (new_role, new_pass, sel_u_id))
                    else: conn.execute("UPDATE users SET role=? WHERE id=?", (new_role, sel_u_id))
                    conn.commit()
                    st.success("تم تحديث بيانات المستخدم.")
                    st.rerun()
                if uc2.button("حذف المستخدم"):
                    if sel_u_id != st.session_state.user_id:
                        conn.execute("DELETE FROM users WHERE id=?", (sel_u_id,))
                        conn.commit()
                        st.success("تم حذف المستخدم.")
                        st.rerun()
                    else: st.error("لا يمكنك حذف حسابك الشخصي أثناء تسجيل الدخول.")

        elif set_sel == "إضافة صنف جديد":
            item_n = st.text_input("اسم الصنف:")
            item_c = st.number_input("التكلفة الافتراضية:", min_value=0.0)
            item_p = st.number_input("سعر البيع:", min_value=0.0)
            if st.button("حفظ الصنف"):
                conn.execute("INSERT INTO items (name, cost_price, sale_price, stock_qty) VALUES (?,?,?,0)", (item_n, item_c, item_p))
                conn.commit()
                st.success("تم إضافة الصنف.")
                
        elif set_sel == "تحديث أسعار الصرف":
            df_cur = pd.read_sql_query("SELECT * FROM currencies", conn)
            st.write("أسعار الصرف الحالية:")
            st.dataframe(df_cur.rename(columns={'code': 'الرمز', 'name': 'العملة', 'exchange_rate': 'سعر الصرف (مقابل الأساسية)'}))
            
            new_c_code = st.text_input("رمز العملة (مثال: YER):", value="YER")
            new_c_name = st.text_input("اسم العملة:", value="ريال يمني")
            new_c_rate = st.number_input("سعر الصرف مقابل الأساسية:", value=0.0071, format="%.4f")
            if st.button("حفظ/تحديث العملة"):
                conn.execute("INSERT OR REPLACE INTO currencies (code, name, exchange_rate) VALUES (?,?,?)", (new_c_code, new_c_name, new_c_rate))
                conn.commit()
                st.success("تم تحديث جدول العملات.")
                st.rerun()
