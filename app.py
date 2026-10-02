import streamlit as st
import sqlite3
import pandas as pd
import re
from datetime import datetime

# ==========================================
# 1. إعداد قاعدة البيانات ودليل الحسابات
# ==========================================
def init_db():
    conn = sqlite3.connect("smart_accounting.db")
    c = conn.cursor()
    c.executescript('''
        CREATE TABLE IF NOT EXISTS accounts (code TEXT PRIMARY KEY, name TEXT, type TEXT);
        CREATE TABLE IF NOT EXISTS journal_entries (id INTEGER KEY, date TEXT, description TEXT);
        CREATE TABLE IF NOT EXISTS journal_lines (
            id INTEGER PRIMARY KEY AUTOINCREMENT, entry_id INTEGER, 
            account_code TEXT, debit REAL, credit REAL
        );
    ''')
    
    # إدراج دليل حسابات مبدئي إذا كان فارغاً
    c.execute("SELECT COUNT(*) FROM accounts")
    if c.fetchone()[0] == 0:
        default_accounts = [
            ("101", "الصندوق (النقدية)", "أصول"),
            ("102", "البنك", "أصول"),
            ("201", "الموردون", "خصوم"),
            ("301", "رأس المال", "حقوق ملكية"),
            ("401", "إيرادات مبيعات", "إيرادات"),
            ("501", "مصروفات الإيجار", "مصروفات"),
            ("502", "مصروفات رواتب", "مصروفات")
        ]
        c.executemany("INSERT INTO accounts VALUES (?,?,?)", default_accounts)
    conn.commit()
    return conn

# ==========================================
# 2. محرك التوجيه الذكي (محاكي الذكاء الاصطناعي)
# ==========================================
def ai_accounting_agent(text):
    """
    هنا يتم استدعاء API لنموذج ذكاء اصطناعي (مثل GPT-4 أو Gemini).
    لجعل النظام يعمل فوراً دون مفاتيح مدفوعة، بنينا محركاً ذكياً محلياً 
    يستخرج المبالغ والتوجيه المحاسبي من النصوص العربية.
    """
    amount_match = re.search(r'\d+', text)
    amount = float(amount_match.group()) if amount_match else 0.0
    
    if amount == 0:
        return None, "عذراً، لم أتمكن من العثور على المبلغ في النص."

    # تحليل النوايا (Intent Recognition)
    if "مبيعات" in text or "بعنا" in text:
        return [
            {"acc": "101", "debit": amount, "credit": 0},      # زيادة النقدية
            {"acc": "401", "debit": 0, "credit": amount}       # زيادة الإيرادات
        ], "قيد إثبات إيرادات مبيعات نقدية"
        
    elif "إيجار" in text:
        return [
            {"acc": "501", "debit": amount, "credit": 0},      # إثبات مصروف
            {"acc": "101", "debit": 0, "credit": amount}       # نقص النقدية
        ], "قيد سداد مصروفات الإيجار نقداً"
        
    elif "رواتب" in text or "راتب" in text:
        return [
            {"acc": "502", "debit": amount, "credit": 0},      # إثبات مصروف
            {"acc": "102", "debit": 0, "credit": amount}       # نقص البنك
        ], "قيد سداد الرواتب عبر البنك"
    else:
        return None, "لم أتمكن من تصنيف العملية. يرجى توضيح النص."

# ==========================================
# 3. محرك ترحيل القيود (القيد المزدوج)
# ==========================================
def post_entry(conn, description, lines):
    total_debit = sum(l['debit'] for l in lines)
    total_credit = sum(l['credit'] for l in lines)
    
    if total_debit != total_credit:
        return False, f"القيد غير متزن! المدين: {total_debit}، الدائن: {total_credit}"
        
    c = conn.cursor()
    # توليد رقم القيد
    c.execute("SELECT MAX(id) FROM journal_entries")
    entry_id = (c.fetchone()[0] or 0) + 1
    date = datetime.now().strftime("%Y-%m-%d %H:%M")
    
    c.execute("INSERT INTO journal_entries VALUES (?,?,?)", (entry_id, date, description))
    for l in lines:
        c.execute("INSERT INTO journal_lines (entry_id, account_code, debit, credit) VALUES (?,?,?,?)",
                  (entry_id, l['acc'], l['debit'], l['credit']))
    conn.commit()
    return True, entry_id

# ==========================================
# 4. واجهة المستخدم (Streamlit Dashboard)
# ==========================================
st.set_page_config(page_title="AI Accounting System", layout="wide")
conn = init_db()

st.title("🤖 النظام المحاسبي الموجه بالذكاء الاصطناعي")

tab1, tab2, tab3 = st.tabs(["إدخال ذكي (AI)", "دفتر اليومية", "ميزان المراجعة"])

# --- التبويب الأول: الإدخال عبر الذكاء الاصطناعي ---
with tab1:
    st.markdown("### أدخل العملية المالية بلغتك الطبيعية")
    st.info("أمثلة للتجربة: 'حققنا مبيعات بقيمة 15000 نقداً' ، 'تم دفع إيجار المكتب 3000' ، 'صرف رواتب الموظفين 8500 من البنك'")
    
    user_input = st.text_input("نص العملية:")
    if st.button("تحليل وترحيل 🚀"):
        if user_input:
            lines, result_msg = ai_accounting_agent(user_input)
            if lines:
                success, msg = post_entry(conn, result_msg, lines)
                if success:
                    st.success(f"✅ تم ترحيل القيد بنجاح برقم {msg}")
                    st.write("**تفاصيل القيد المُنشأ آلياً:**")
                    st.table(pd.DataFrame(lines).rename(columns={'acc': 'رقم الحساب', 'debit': 'مدين', 'credit': 'دائن'}))
                else:
                    st.error(msg)
            else:
                st.warning(result_msg)

# --- التبويب الثاني: دفتر اليومية ---
with tab2:
    st.markdown("### دفتر القيود اليومية")
    query = """
        SELECT e.date AS التاريخ, e.description AS البيان, a.name AS الحساب, 
               l.debit AS مدين, l.credit AS دائن
        FROM journal_entries e
        JOIN journal_lines l ON e.id = l.entry_id
        JOIN accounts a ON l.account_code = a.code
        ORDER BY e.id DESC
    """
    df_journal = pd.read_sql_query(query, conn)
    st.dataframe(df_journal, use_container_width=True)

# --- التبويب الثالث: ميزان المراجعة والأرصدة ---
with tab3:
    st.markdown("### ميزان المراجعة اللحظي")
    query_tb = """
        SELECT a.code AS رقم_الحساب, a.name AS اسم_الحساب, 
               SUM(l.debit) AS إجمالي_المدين, SUM(l.credit) AS إجمالي_الدائن,
               (SUM(l.debit) - SUM(l.credit)) AS الرصيد
        FROM accounts a
        LEFT JOIN journal_lines l ON a.code = l.account_code
        GROUP BY a.code
        HAVING الرصيد != 0 OR إجمالي_المدين > 0
    """
    df_tb = pd.read_sql_query(query_tb, conn)
    if not df_tb.empty:
        # تعديل الرصيد ليظهر مديناً أو دائناً
        df_tb['طبيعة الرصيد'] = df_tb['الرصيد'].apply(lambda x: "مدين" if x > 0 else "دائن")
        df_tb['الرصيد'] = df_tb['الرصيد'].abs()
        st.dataframe(df_tb, use_container_width=True)
    else:
        st.info("لا توجد حركات بعد لتكوين ميزان المراجعة.")
