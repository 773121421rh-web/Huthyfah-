import streamlit as st
import sqlite3
import pandas as pd
import re
from datetime import datetime

# ==========================================
# 1. تهيئة قاعدة البيانات الشاملة
# ==========================================
def init_db():
    conn = sqlite3.connect("enterprise_accounting.db")
    c = conn.cursor()
    c.executescript('''
        CREATE TABLE IF NOT EXISTS accounts (code TEXT PRIMARY KEY, name TEXT, type TEXT);
        CREATE TABLE IF NOT EXISTS journal_entries (id INTEGER PRIMARY KEY AUTOINCREMENT, date TEXT, description TEXT);
        CREATE TABLE IF NOT EXISTS journal_lines (
            id INTEGER PRIMARY KEY AUTOINCREMENT, entry_id INTEGER, 
            account_code TEXT, debit REAL, credit REAL
        );
        CREATE TABLE IF NOT EXISTS employees (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, basic_salary REAL);
    ''')
    
    # بناء شجرة حسابات متقدمة
    c.execute("SELECT COUNT(*) FROM accounts")
    if c.fetchone()[0] == 0:
        default_accounts = [
            ("101", "النقدية بالصندوق", "أصول"),
            ("102", "النقدية بالبنك", "أصول"),
            ("103", "المخزون", "أصول"),
            ("104", "العملاء (ذمم مدينة)", "أصول"),
            ("201", "الموردون (ذمم دائنة)", "خصوم"),
            ("301", "رأس المال", "حقوق ملكية"),
            ("401", "إيرادات المبيعات", "إيرادات"),
            ("501", "تكلفة البضاعة المباعة", "مصروفات"),
            ("502", "مصروفات الرواتب والأجور", "مصروفات"),
            ("503", "مصروفات الإيجار", "مصروفات")
        ]
        c.executemany("INSERT INTO accounts VALUES (?,?,?)", default_accounts)
        
        # إضافة موظف افتراضي للتجربة
        c.execute("INSERT INTO employees (name, basic_salary) VALUES ('أحمد محمد', 5000)")
    conn.commit()
    return conn

# ==========================================
# 2. محرك الترحيل والقيد المزدوج
# ==========================================
def post_entry(conn, description, lines):
    total_debit = sum(l['debit'] for l in lines)
    total_credit = sum(l['credit'] for l in lines)
    if round(total_debit, 2) != round(total_credit, 2):
        return False, f"القيد غير متزن! المدين: {total_debit}، الدائن: {total_credit}"
    
    c = conn.cursor()
    date = datetime.now().strftime("%Y-%m-%d %H:%M")
    c.execute("INSERT INTO journal_entries (date, description) VALUES (?,?)", (date, description))
    entry_id = c.lastrowid
    
    for l in lines:
        c.execute("INSERT INTO journal_lines (entry_id, account_code, debit, credit) VALUES (?,?,?,?)", 
                  (entry_id, l['acc'], l['debit'], l['credit']))
    conn.commit()
    return True, entry_id

# ==========================================
# 3. واجهة النظام (Streamlit Dashboard)
# ==========================================
st.set_page_config(page_title="ERP Accounting System", layout="wide")
conn = init_db()

st.title("🏢 نظام إدارة الموارد والمحاسبة المتكامل")

# تقسيم النظام إلى وحدات (Tabs)
tab_ai, tab_trade, tab_hr, tab_manual, tab_reports = st.tabs([
    "🤖 المساعد الذكي", 
    "🛒 المبيعات والمشتريات", 
    "👥 شؤون الموظفين", 
    "✍️ قيود وأرصدة", 
    "📊 التقارير المالية"
])

# --- الوحدة الأولى: المساعد الذكي ---
with tab_ai:
    st.markdown("### الإدخال السريع باللغة الطبيعية")
    user_input = st.text_input("صف العملية (مثال: دفعنا إيجار 3000 من البنك، أو بعنا بضاعة بـ 15000 نقداً):")
    if st.button("تحليل ذكي 🚀"):
        amount_match = re.search(r'\d+', user_input)
        amount = float(amount_match.group()) if amount_match else 0.0
        if amount > 0:
            lines = []
            desc = user_input
            if "إيجار" in user_input:
                acc_cash = "102" if "بنك" in user_input else "101"
                lines = [{"acc": "503", "debit": amount, "credit": 0}, {"acc": acc_cash, "debit": 0, "credit": amount}]
            elif "مبيعات" in user_input or "بعنا" in user_input:
                lines = [{"acc": "101", "debit": amount, "credit": 0}, {"acc": "401", "debit": 0, "credit": amount}]
            
            if lines:
                success, msg = post_entry(conn, desc, lines)
                if success: st.success("✅ تم ترحيل القيد آلياً.")
                else: st.error(msg)
            else:
                st.warning("لم أتعرف على نوع العملية. استخدم شاشة القيود اليدوية.")
        else:
            st.error("الرجاء كتابة المبلغ كأرقام.")

# --- الوحدة الثانية: المبيعات والمشتريات ---
with tab_trade:
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("### 🛒 فاتورة مشتريات")
        pur_amount = st.number_input("قيمة المشتريات", min_value=0.0, step=100.0)
        pur_method = st.selectbox("طريقة الدفع", ["نقداً (صندوق)", "آجل (موردون)"], key="pur_method")
        if st.button("إثبات المشتريات"):
            if pur_amount > 0:
                credit_acc = "101" if "نقداً" in pur_method else "201"
                lines = [
                    {"acc": "103", "debit": pur_amount, "credit": 0}, # زيادة المخزون
                    {"acc": credit_acc, "debit": 0, "credit": pur_amount}
                ]
                success, _ = post_entry(conn, f"مشتريات بضاعة - {pur_method}", lines)
                if success: st.success("تم تسجيل المشتريات.")
                
    with col2:
        st.markdown("### 💰 فاتورة مبيعات")
        sales_amount = st.number_input("قيمة المبيعات", min_value=0.0, step=100.0)
        cost_amount = st.number_input("تكلفة البضاعة المباعة (لخصمها من المخزون)", min_value=0.0, step=100.0)
        if st.button("إثبات المبيعات"):
            if sales_amount > 0 and cost_amount > 0:
                lines = [
                    {"acc": "101", "debit": sales_amount, "credit": 0}, # استلام النقد
                    {"acc": "401", "debit": 0, "credit": sales_amount}, # إيراد
                    {"acc": "501", "debit": cost_amount, "credit": 0},  # تكلفة المبيعات
                    {"acc": "103", "debit": 0, "credit": cost_amount}   # خفض المخزون
                ]
                success, _ = post_entry(conn, "مبيعات بضاعة نقدية", lines)
                if success: st.success("تم تسجيل المبيعات وخصم المخزون.")

# --- الوحدة الثالثة: الموارد البشرية والرواتب ---
with tab_hr:
    st.markdown("### 👥 إدارة الموظفين وصرف الرواتب")
    df_emp = pd.read_sql_query("SELECT id, name AS الموظف, basic_salary AS الراتب_الأساسي FROM employees", conn)
    st.dataframe(df_emp, use_container_width=True)
    
    total_salaries = df_emp['الراتب_الأساسي'].sum()
    st.info(f"إجمالي مسير الرواتب المستحق: {total_salaries}")
    
    if st.button("صرف رواتب جميع الموظفين (من البنك)"):
        if total_salaries > 0:
            lines = [
                {"acc": "502", "debit": total_salaries, "credit": 0}, # مصروف رواتب
                {"acc": "102", "debit": 0, "credit": total_salaries}  # نقص البنك
            ]
            success, _ = post_entry(conn, "صرف مسير رواتب الموظفين", lines)
            if success: st.success("تم صرف الرواتب وتوليد القيد المحاسبي.")

# --- الوحدة الرابعة: القيود اليدوية والأرصدة الافتتاحية ---
with tab_manual:
    st.markdown("### ✍️ إدخال قيد مركب / أرصدة افتتاحية")
    accounts_df = pd.read_sql_query("SELECT code, name FROM accounts", conn)
    acc_list = accounts_df['code'].astype(str) + " - " + accounts_df['name']
    
    if 'manual_lines' not in st.session_state:
        st.session_state.manual_lines = pd.DataFrame([
            {"الحساب": "101 - النقدية بالصندوق", "مدين": 0.0, "دائن": 0.0},
            {"الحساب": "102 - النقدية بالبنك", "مدين": 0.0, "دائن": 0.0},
            {"الحساب": "301 - رأس المال", "مدين": 0.0, "دائن": 0.0}
        ])
        
    edited_df = st.data_editor(
        st.session_state.manual_lines, 
        column_config={"الحساب": st.column_config.SelectboxColumn("الحساب", options=acc_list.tolist(), required=True)},
        num_rows="dynamic", use_container_width=True
    )
    desc = st.text_input("البيان:", "قيد افتتاحي")
    
    if st.button("ترحيل القيد المزدوج"):
        lines_to_post = []
        for _, row in edited_df.iterrows():
            if row['مدين'] > 0 or row['دائن'] > 0:
                acc_code = str(row['الحساب']).split(" - ")[0]
                lines_to_post.append({"acc": acc_code, "debit": float(row['مدين']), "credit": float(row['دائن'])})
        if lines_to_post:
            success, msg = post_entry(conn, desc, lines_to_post)
            if success: st.success("✅ تم ترحيل القيد بنجاح!")
            else: st.error(msg)

# --- الوحدة الخامسة: التقارير المالية والإدارية ---
with tab_reports:
    rep_type = st.radio("اختر التقرير:", ["دفتر اليومية", "ميزان المراجعة", "قائمة الدخل (الأرباح والخسائر)"], horizontal=True)
    
    if rep_type == "دفتر اليومية":
        query = "SELECT e.id AS رقم_القيد, e.date AS التاريخ, e.description AS البيان, a.name AS الحساب, l.debit AS مدين, l.credit AS دائن FROM journal_entries e JOIN journal_lines l ON e.id = l.entry_id JOIN accounts a ON l.account_code = a.code ORDER BY e.id DESC"
        st.dataframe(pd.read_sql_query(query, conn), use_container_width=True)
        
    elif rep_type == "ميزان المراجعة":
        query_tb = "SELECT a.code AS رقم_الحساب, a.name AS اسم_الحساب, a.type AS التصنيف, SUM(l.debit) AS إجمالي_المدين, SUM(l.credit) AS إجمالي_الدائن, (SUM(l.debit) - SUM(l.credit)) AS الرصيد FROM accounts a LEFT JOIN journal_lines l ON a.code = l.account_code GROUP BY a.code HAVING الرصيد != 0 OR إجمالي_المدين > 0"
        df_tb = pd.read_sql_query(query_tb, conn)
        if not df_tb.empty:
            df_tb['طبيعة الرصيد'] = df_tb['الرصيد'].apply(lambda x: "مدين" if x > 0 else "دائن")
            df_tb['الرصيد'] = df_tb['الرصيد'].abs()
            st.dataframe(df_tb, use_container_width=True)
            
    elif rep_type == "قائمة الدخل (الأرباح والخسائر)":
        query_pl = "SELECT a.name AS البند, a.type AS النوع, SUM(l.credit) - SUM(l.debit) AS القيمة FROM accounts a JOIN journal_lines l ON a.code = l.account_code WHERE a.type IN ('إيرادات', 'مصروفات') GROUP BY a.code"
        df_pl = pd.read_sql_query(query_pl, conn)
        if not df_pl.empty:
            # عكس إشارة المصروفات لتظهر كقيم موجبة في التقرير
            df_pl.loc[df_pl['النوع'] == 'مصروفات', 'القيمة'] = df_pl['القيمة'] * -1
            
            st.table(df_pl[['البند', 'القيمة']])
            
            revenues = df_pl[df_pl['النوع'] == 'إيرادات']['القيمة'].sum()
            expenses = df_pl[df_pl['النوع'] == 'مصروفات']['القيمة'].sum()
            net_income = revenues - expenses
            
            st.metric(label="صافي الربح / (الخسارة)", value=f"{net_income:,.2f}")
        else:
            st.info("لا توجد حركات على حسابات الإيرادات والمصروفات بعد.")
