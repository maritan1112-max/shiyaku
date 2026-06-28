import streamlit as st
from databricks import sql
import pandas as pd
from datetime import date, datetime
import os

# ページ設定
st.set_page_config(
    page_title="試薬管理システム",
    page_icon="🧪",
    layout="wide"
)

# Databricks 接続設定（Apps環境では環境変数から自動取得）
def get_connection():
    return sql.connect(
        server_hostname="dbc-36982739-dae7.cloud.databricks.com",
        http_path="/sql/1.0/warehouses/b3607f97055adf7a",
        access_token="dapie751f6cae68995457f768b5d8678bfca"
    )

# データ取得関数
@st.cache_data(ttl=30)
def load_reagents():
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT m.reagent_id, m.name, m.manufacturer, m.unit,
                       m.storage_temp, m.hazard_class,
                       COALESCE(SUM(s.quantity), 0) AS total_stock,
                       MIN(s.expiry_date) AS nearest_expiry
                FROM lab_management.reagents.reagent_master m
                LEFT JOIN lab_management.reagents.reagent_stock s
                  ON m.reagent_id = s.reagent_id AND s.status = 'active'
                GROUP BY m.reagent_id, m.name, m.manufacturer,
                         m.unit, m.storage_temp, m.hazard_class
                ORDER BY m.name
            """)
            return pd.DataFrame(cursor.fetchall(),
                                columns=[d[0] for d in cursor.description])

@st.cache_data(ttl=30)
def load_expiring_soon(days=30):
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(f"""
                SELECT m.name, s.lot_number, s.quantity, m.unit,
                       s.expiry_date, s.location,
                       DATEDIFF(s.expiry_date, CURRENT_DATE) AS days_left
                FROM lab_management.reagents.reagent_stock s
                JOIN lab_management.reagents.reagent_master m
                  ON s.reagent_id = m.reagent_id
                WHERE s.status = 'active'
                  AND s.expiry_date <= DATE_ADD(CURRENT_DATE, {days})
                ORDER BY s.expiry_date
            """)
            return pd.DataFrame(cursor.fetchall(),
                                columns=[d[0] for d in cursor.description])

# サイドバーナビゲーション
st.sidebar.title("🧪 試薬管理システム")
page = st.sidebar.radio("メニュー", [
    "📊 在庫一覧",
    "⚠️ 期限アラート",
    "📥 入庫登録",
    "📤 出庫登録",
    "➕ 試薬マスタ登録",
    "📋 履歴照会"
])

# ========== 在庫一覧 ==========
if page == "📊 在庫一覧":
    st.title("📊 試薬在庫一覧")
    df = load_reagents()

    col1, col2, col3 = st.columns(3)
    col1.metric("試薬種類数", f"{len(df)} 種")
    col2.metric("在庫切れ", f"{(df['total_stock'] == 0).sum()} 種")
    col3.metric("期限切れ間近（30日以内）", f"{len(load_expiring_soon(30))} ロット")

    # フィルター
    search = st.text_input("🔍 試薬名で検索")
    if search:
        df = df[df['name'].str.contains(search, case=False, na=False)]

    storage_filter = st.multiselect("保管温度で絞り込み",
                                     df['storage_temp'].dropna().unique())
    if storage_filter:
        df = df[df['storage_temp'].isin(storage_filter)]

    # 在庫ゼロを赤くハイライト
    def highlight_zero(row):
        if row['total_stock'] == 0:
            return ['background-color: #ffcccc'] * len(row)
        return [''] * len(row)

    st.dataframe(df.style.apply(highlight_zero, axis=1),
                 use_container_width=True)

# ========== 期限アラート ==========
elif page == "⚠️ 期限アラート":
    st.title("⚠️ 使用期限アラート")
    days = st.slider("何日以内の期限を表示？", 7, 90, 30)
    df = load_expiring_soon(days)

    if df.empty:
        st.success(f"✅ {days}日以内に期限切れになる試薬はありません")
    else:
        st.warning(f"⚠️ {len(df)} ロットが {days} 日以内に期限切れになります")
        # 残り日数で色分け
        def color_days(val):
            if val <= 7:
                return 'background-color: #ff4444; color: white'
            elif val <= 14:
                return 'background-color: #ffaa00'
            return ''
        st.dataframe(
            df.style.applymap(color_days, subset=['days_left']),
            use_container_width=True
        )

# ========== 入庫登録 ==========
elif page == "📥 入庫登録":
    st.title("📥 入庫登録")
    reagents_df = load_reagents()
    reagent_names = reagents_df['name'].tolist()

    with st.form("inbound_form"):
        selected = st.selectbox("試薬名", reagent_names)
        col1, col2 = st.columns(2)
        lot = col1.text_input("ロット番号")
        qty = col2.number_input("入庫数量", min_value=0.0, step=0.1)
        col3, col4 = st.columns(2)
        location = col3.text_input("保管場所（棚番号）")
        expiry = col4.date_input("使用期限", value=date.today())
        notes = st.text_area("備考")
        submitted = st.form_submit_button("✅ 入庫登録")

    if submitted:
        reagent_id = int(reagents_df[reagents_df['name'] == selected]['reagent_id'].iloc[0])
        with get_connection() as conn:
            with conn.cursor() as cursor:
                # 在庫テーブルに追加
                cursor.execute("""
                    INSERT INTO lab_management.reagents.reagent_stock
                      (reagent_id, lot_number, quantity, location, expiry_date, received_date)
                    VALUES (?, ?, ?, ?, ?, CURRENT_DATE)
                """, [reagent_id, lot, qty, location, expiry.isoformat()])
                # 履歴に記録
                cursor.execute("""
                    INSERT INTO lab_management.reagents.reagent_transactions
                      (stock_id, tx_type, quantity, user_name, notes)
                    SELECT MAX(stock_id), 'in', ?, current_user(), ?
                    FROM lab_management.reagents.reagent_stock
                """, [qty, notes])
        st.success(f"✅ {selected}（{qty}）を入庫登録しました")
        st.cache_data.clear()

# ========== 出庫登録 ==========
elif page == "📤 出庫登録":
    st.title("📤 出庫登録")
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT s.stock_id, m.name, s.lot_number, s.quantity, m.unit, s.expiry_date
                FROM lab_management.reagents.reagent_stock s
                JOIN lab_management.reagents.reagent_master m ON s.reagent_id = m.reagent_id
                WHERE s.status = 'active' AND s.quantity > 0
                ORDER BY m.name, s.expiry_date
            """)
            stocks = pd.DataFrame(cursor.fetchall(),
                                  columns=[d[0] for d in cursor.description])

    if stocks.empty:
        st.info("出庫可能な在庫がありません")
    else:
        stocks['label'] = stocks['name'] + " / Lot:" + stocks['lot_number'].fillna('') + \
                          " / 残:" + stocks['quantity'].astype(str) + stocks['unit'].fillna('')
        with st.form("outbound_form"):
            selected_label = st.selectbox("試薬・ロット選択", stocks['label'])
            selected_row = stocks[stocks['label'] == selected_label].iloc[0]
            qty_out = st.number_input("出庫数量",
                                      min_value=0.01,
                                      max_value=float(selected_row['quantity']),
                                      step=0.1)
            purpose = st.text_input("使用目的・実験名")
            submitted = st.form_submit_button("✅ 出庫登録")

        if submitted:
            stock_id = int(selected_row['stock_id'])
            with get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("""
                        UPDATE lab_management.reagents.reagent_stock
                        SET quantity = quantity - ?
                        WHERE stock_id = ?
                    """, [qty_out, stock_id])
                    cursor.execute("""
                        INSERT INTO lab_management.reagents.reagent_transactions
                          (stock_id, tx_type, quantity, user_name, purpose)
                        VALUES (?, 'out', ?, current_user(), ?)
                    """, [stock_id, -qty_out, purpose])
            st.success(f"✅ 出庫登録しました（{qty_out} {selected_row['unit']}）")
            st.cache_data.clear()

# ========== 試薬マスタ登録 ==========
elif page == "➕ 試薬マスタ登録":
    st.title("➕ 試薬マスタ登録")
    with st.form("master_form"):
        name = st.text_input("試薬名 *", placeholder="例：エタノール 99.5%")
        col1, col2 = st.columns(2)
        cas = col1.text_input("CAS番号", placeholder="例：64-17-5")
        manufacturer = col2.text_input("メーカー")
        col3, col4 = st.columns(2)
        unit = col3.selectbox("単位", ["mL", "L", "g", "kg", "本", "個", "箱"])
        storage = col4.selectbox("保管温度", ["室温", "冷蔵（2-8℃）", "冷凍（-20℃）", "冷凍（-80℃）"])
        hazard = st.selectbox("危険物区分", ["なし", "引火性液体", "腐食性", "毒物", "劇物", "その他"])
        submitted = st.form_submit_button("✅ 登録")

    if submitted and name:
        with get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("""
                    INSERT INTO lab_management.reagents.reagent_master
                      (name, cas_number, manufacturer, unit, storage_temp, hazard_class)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, [name, cas, manufacturer, unit, storage, hazard])
        st.success(f"✅ 「{name}」をマスタに登録しました")
        st.cache_data.clear()

# ========== 履歴照会 ==========
elif page == "📋 履歴照会":
    st.title("📋 入出庫履歴")
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT t.tx_date, m.name, s.lot_number,
                       t.tx_type, t.quantity, m.unit,
                       t.user_name, t.purpose, t.notes
                FROM lab_management.reagents.reagent_transactions t
                JOIN lab_management.reagents.reagent_stock s ON t.stock_id = s.stock_id
                JOIN lab_management.reagents.reagent_master m ON s.reagent_id = m.reagent_id
                ORDER BY t.tx_date DESC
                LIMIT 200
            """)
            df = pd.DataFrame(cursor.fetchall(),
                              columns=[d[0] for d in cursor.description])
    st.dataframe(df, use_container_width=True)
    csv = df.to_csv(index=False).encode('utf-8-sig')
    st.download_button("📥 CSVダウンロード", csv, "reagent_history.csv", "text/csv")
