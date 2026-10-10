import streamlit as st
import pandas as pd
import numpy as np
import folium
from folium.plugins import MarkerCluster
from streamlit_folium import st_folium
import plotly.express as px

st.set_page_config(
    layout="wide",
    page_title="Витрина новостроек",
    page_icon="🏙",
)

st.markdown("""
<style>
.zhk-card {
    border: 1px solid #e6e6e6;
    border-radius: 12px;
    padding: 20px;
    margin-bottom: 16px;
    background: #ffffff;
    box-shadow: 0 1px 3px rgba(0,0,0,0.04);
    cursor: pointer;
}
.zhk-card:hover {
    box-shadow: 0 4px 12px rgba(0,0,0,0.08);
    border-color: #cfd8ff;
}
.zhk-title {
    font-size: 22px;
    font-weight: 700;
    margin-bottom: 6px;
    color: #1a1a1a;
}
.zhk-sub {
    color: #666;
    font-size: 14px;
    margin-bottom: 10px;
}
.zhk-price {
    font-size: 26px;
    font-weight: 700;
    color: #0d7a3f;
    margin: 10px 0;
}
.zhk-badge {
    display: inline-block;
    padding: 4px 12px;
    border-radius: 12px;
    font-size: 13px;
    margin: 2px 6px 2px 0;
    background: #eef3ff;
    color: #2b4d9b;
}
.zhk-badge-green {
    background: #e7f6ec;
    color: #0d7a3f;
}
.zhk-badge-warn {
    background: #fff4e5;
    color: #b05a00;
}
</style>
""", unsafe_allow_html=True)


@st.cache_data
def load():
    df = pd.read_csv("production_data_merged.csv")

    num_cols = [
        "price_rub", "price_per_sqm", "price_mln",
        "total_area", "living_area", "kitchen_area",
        "floor", "total_floors", "ceiling_height",
        "metro_distance_min", "completion_year", "build_year",
        "lat", "lon", "views",
    ]
    for c in num_cols:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")

    if "rooms" in df.columns:
        df["rooms"] = pd.to_numeric(df["rooms"], errors="coerce").fillna(0).astype(int)

    if "price_mln" not in df.columns and "price_rub" in df.columns:
        df["price_mln"] = df["price_rub"] / 1_000_000

    if "price_per_sqm" not in df.columns and "price_rub" in df.columns and "total_area" in df.columns:
        df["price_per_sqm"] = df["price_rub"] / df["total_area"]

    if "metro_distance_min" in df.columns:
        df["metro_distance_min"] = pd.to_numeric(df["metro_distance_min"], errors="coerce")
        df.loc[df["metro_distance_min"] > 90, "metro_distance_min"] = np.nan
        df.loc[df["metro_distance_min"] < 0, "metro_distance_min"] = np.nan

    df = df.loc[:, ~df.columns.duplicated()]

    if "id" not in df.columns:
        df["id"] = df.index.astype(str)
    df["id"] = df["id"].astype(str)

    return df


df = load()

if df.empty:
    st.error("Файл production_data_merged.csv пуст или не найден.")
    st.stop()

# --- session state ---
if "favorites" not in st.session_state:
    st.session_state.favorites = set()
if "selected_zhk" not in st.session_state:
    st.session_state.selected_zhk = None
if "card_page" not in st.session_state:
    st.session_state.card_page = 1
# Вкладка, которую нужно активировать при следующем рендере
if "active_tab" not in st.session_state:
    st.session_state.active_tab = "🏠 Карточки"
# Метка для переключения (используется как key у st.tabs через radio-эмуляцию)


def toggle_fav(zhk_id):
    if zhk_id in st.session_state.favorites:
        st.session_state.favorites.remove(zhk_id)
    else:
        st.session_state.favorites.add(zhk_id)


def open_card(zhk_id, switch_tab=True):
    st.session_state.selected_zhk = zhk_id
    if switch_tab:
        st.session_state.active_tab = "📄 Карточка"


def reset_filters():
    for k in list(st.session_state.keys()):
        if k.startswith("flt_"):
            del st.session_state[k]
    st.session_state.card_page = 1


def fmt_price(row):
    if pd.notna(row.get("price_mln")):
        return f"{row['price_mln']:.2f} млн ₽"
    if pd.notna(row.get("price_rub")):
        return f"{int(row['price_rub']):,} ₽".replace(",", " ")
    return "цена не указана"


def fmt_metro(row):
    name = row.get("metro_station")
    dist = row.get("metro_distance_min")
    if pd.isna(name) and pd.isna(dist):
        return "нет метро"
    if pd.isna(name):
        return f"{int(dist)} мин"
    if pd.isna(dist):
        return str(name)
    return f"{name} · {int(dist)} мин"


METRO_MAX_REAL = (
    int(np.nanmax(df["metro_distance_min"]))
    if "metro_distance_min" in df.columns and df["metro_distance_min"].notna().any()
    else 999
)


with st.sidebar:
    st.header("🔍 Фильтры")
    st.button("♻️ Сбросить фильтры", on_click=reset_filters, use_container_width=True)

    if "city" in df.columns:
        cities = sorted(df["city"].dropna().unique().tolist())
        sel_cities = st.multiselect(
            "Город", cities,
            default=st.session_state.get("flt_cities", []),
            key="flt_cities",
        )
    else:
        sel_cities = []

    if "source" in df.columns:
        sources = sorted(df["source"].dropna().unique().tolist())
        sel_sources = st.multiselect(
            "Источник данных", sources,
            default=st.session_state.get("flt_sources", sources),
            key="flt_sources",
        )
    else:
        sel_sources = []

    if "developer" in df.columns:
        developers = sorted(df["developer"].dropna().unique().tolist())
        sel_devs = st.multiselect(
            "Застройщик", developers,
            default=st.session_state.get("flt_devs", []),
            key="flt_devs",
        )
    else:
        sel_devs = []

    if "complex_class" in df.columns:
        classes = sorted(df["complex_class"].dropna().unique().tolist())
        sel_classes = st.multiselect(
            "Класс ЖК", classes,
            default=st.session_state.get("flt_classes", []),
            key="flt_classes",
        )
    else:
        sel_classes = []

    st.markdown("**Цена, млн ₽**")
    col_p1, col_p2 = st.columns(2)
    price_from = col_p1.number_input(
        "от", min_value=0.0,
        value=st.session_state.get("flt_price_from", 0.0),
        step=0.5, key="flt_price_from", label_visibility="collapsed",
    )
    price_to = col_p2.number_input(
        "до", min_value=0.0,
        value=st.session_state.get(
            "flt_price_to",
            float(np.nanmax(df["price_mln"])) if "price_mln" in df and df["price_mln"].notna().any() else 0.0,
        ),
        step=0.5, key="flt_price_to", label_visibility="collapsed",
    )
    st.caption("от / до")

    st.markdown("**Этаж**")
    col_f1, col_f2 = st.columns(2)
    floor_from = col_f1.number_input(
        "от ", min_value=0,
        value=st.session_state.get("flt_floor_from", 0),
        step=1, key="flt_floor_from", label_visibility="collapsed",
    )
    floor_to = col_f2.number_input(
        "до ", min_value=0,
        value=st.session_state.get(
            "flt_floor_to",
            int(np.nanmax(df["floor"])) if "floor" in df and df["floor"].notna().any() else 100,
        ),
        step=1, key="flt_floor_to", label_visibility="collapsed",
    )
    st.caption("от / до")

    st.markdown("**До метро, мин**")
    if "metro_distance_min" in df.columns and df["metro_distance_min"].notna().any():
        m_max_real = METRO_MAX_REAL
        col_m1, col_m2 = st.columns(2)
        metro_from = col_m1.number_input(
            "от  ", min_value=0,
            value=st.session_state.get("flt_metro_from", 0),
            step=1, key="flt_metro_from", label_visibility="collapsed",
        )
        metro_to = col_m2.number_input(
            "до  ", min_value=0,
            value=st.session_state.get("flt_metro_to", m_max_real),
            step=1, key="flt_metro_to", label_visibility="collapsed",
        )
        st.caption("от / до")
        st.caption("⚠️ При сужении диапазона объекты без метро скрываются")
    else:
        metro_from, metro_to = 0, 999

    if "rooms" in df.columns:
        rooms_all = sorted(df["rooms"].dropna().unique().tolist())
        sel_rooms = st.multiselect(
            "Комнат", rooms_all,
            default=st.session_state.get("flt_rooms", []),
            key="flt_rooms",
        )
    else:
        sel_rooms = []

    area_from = st.number_input(
        "Площадь от, м²", min_value=0.0,
        value=st.session_state.get("flt_area_from", 0.0),
        step=1.0, key="flt_area_from",
    )

    only_mortgage = st.checkbox(
        "Только со льготной ипотекой",
        value=st.session_state.get("flt_mortgage", False),
        key="flt_mortgage",
    )


f = df.copy()

if sel_cities:
    f = f[f["city"].isin(sel_cities)]
if sel_sources:
    f = f[f["source"].isin(sel_sources)]
if sel_devs:
    f = f[f["developer"].isin(sel_devs)]
if sel_classes:
    f = f[f["complex_class"].isin(sel_classes)]
if sel_rooms:
    f = f[f["rooms"].isin(sel_rooms)]

if "price_mln" in f.columns:
    f = f[(f["price_mln"].between(price_from, price_to)) | f["price_mln"].isna()]
if "floor" in f.columns:
    f = f[(f["floor"].between(floor_from, floor_to)) | f["floor"].isna()]
if "total_area" in f.columns and area_from > 0:
    f = f[(f["total_area"] >= area_from) | f["total_area"].isna()]

if "metro_distance_min" in f.columns:
    m_max_real = METRO_MAX_REAL
    metro_filter_active = (metro_from > 0) or (metro_to < m_max_real)

    if metro_filter_active:
        f = f[
            f["metro_distance_min"].notna() &
            f["metro_distance_min"].between(metro_from, metro_to)
        ]
    else:
        f = f[
            f["metro_distance_min"].between(metro_from, metro_to) |
            f["metro_distance_min"].isna()
        ]

if only_mortgage and "mortgage_allowed" in f.columns:
    f = f[f["mortgage_allowed"] == True]

f = f.reset_index(drop=True)


def render_card(row, key_prefix, full=False, show_open_button=True):
    zhk_id = str(row["id"])
    is_fav = zhk_id in st.session_state.favorites

    col_left, col_right = st.columns([6, 1])

    with col_left:
        st.markdown(f"""
        <div class="zhk-card">
            <div class="zhk-title">{row.get('complex_name', 'ЖК без названия')}</div>
            <div class="zhk-sub">{row.get('developer', '—')} · {row.get('city', '')} {row.get('district', '') or ''}</div>
            <div>
                <span class="zhk-badge">{row.get('complex_class', 'класс не указан')}</span>
                <span class="zhk-badge">{row.get('rooms', '—')} комн</span>
                <span class="zhk-badge">{row.get('total_area', '—')} м²</span>
                <span class="zhk-badge">этаж {row.get('floor', '—')} из {row.get('total_floors', '—')}</span>
                <span class="zhk-badge-green zhk-badge">{fmt_metro(row)}</span>
            </div>
            <div class="zhk-price">{fmt_price(row)}</div>
            <div class="zhk-sub">
                Сдача: {row.get('completion_year', '—')} ·
                Статус: {row.get('status', '—')} ·
                Источник: {row.get('source', '—')}
            </div>
        </div>
        """, unsafe_allow_html=True)

        # Кнопка "Открыть карточку" поверх карточки — на весь блок по ширине
        if not full:
            if st.button(
                "📄 Открыть подробную карточку",
                key=f"{key_prefix}_openbtn_{zhk_id}",
                use_container_width=True,
            ):
                open_card(zhk_id, switch_tab=True)
                st.rerun()

        if full:
            fields = [
                ("Комнат", row.get("rooms")),
                ("Общая площадь", f"{row.get('total_area')} м²" if pd.notna(row.get("total_area")) else "—"),
                ("Жилая площадь", f"{row.get('living_area')} м²" if pd.notna(row.get("living_area")) else "—"),
                ("Кухня", f"{row.get('kitchen_area')} м²" if pd.notna(row.get("kitchen_area")) else "—"),
                ("Этаж", row.get("floor")),
                ("Этажей в доме", row.get("total_floors")),
                ("Потолки", f"{row.get('ceiling_height')} м" if pd.notna(row.get("ceiling_height")) else "—"),
                ("Метро", fmt_metro(row)),
                ("Год сдачи", row.get("completion_year")),
                ("Статус", row.get("status")),
                ("Класс", row.get("complex_class")),
                ("Застройщик", row.get("developer")),
                ("Город", row.get("city")),
                ("Район", row.get("district")),
                ("Отделка", row.get("decoration")),
                ("Источник", row.get("source")),
                ("₽/м²", f"{int(row.get('price_per_sqm')):,}".replace(",", " ") if pd.notna(row.get("price_per_sqm")) else "—"),
            ]
            st.markdown("#### Характеристики")
            cols = st.columns(3)
            for i, (label, val) in enumerate(fields):
                cols[i % 3].markdown(f"**{label}:** {val if pd.notna(val) else '—'}")

            if pd.notna(row.get("url")):
                st.markdown(f"🔗 [Открыть на {row.get('source', 'сайте')}]({row['url']})")
        else:
            if pd.notna(row.get("url")):
                st.markdown(f"[🔗 Открыть на {row.get('source', 'сайте')}]({row['url']})")

    with col_right:
        label = "💔 Убрать" if is_fav else "❤ В избранное"
        if st.button(label, key=f"{key_prefix}_fav_{zhk_id}"):
            toggle_fav(zhk_id)
            st.rerun()


# --- Кастомные табы с управлением из session_state ---
TABS = [
    "🏠 Карточки",
    "🗺 Карта",
    "📄 Карточка",
    f"❤ Избранное ({len(st.session_state.favorites)})",
    "📊 Аналитика",
]

# Текущий активный таб (с защитой от изменения списка вкладок)
if st.session_state.active_tab not in TABS:
    # Если вкладка избранного изменила название (число), оставляем Карточки
    if st.session_state.active_tab.startswith("❤ Избранное"):
        st.session_state.active_tab = "❤ Избранное"
    else:
        st.session_state.active_tab = "🏠 Карточки"

# Радио-переключатель, стилизованный под табы
tab_labels = ["🏠 Карточки", "🗺 Карта", "📄 Карточка", "❤ Избранное", "📊 Аналитика"]
active_index = tab_labels.index(
    st.session_state.active_tab if st.session_state.active_tab in tab_labels else "🏠 Карточки"
)

selected_tab = st.radio(
    "Навигация",
    tab_labels,
    index=active_index,
    horizontal=True,
    label_visibility="collapsed",
    key="nav_radio",
)

# Синхронизация: если пользователь кликнул вручную — обновляем session_state
if selected_tab != st.session_state.active_tab:
    st.session_state.active_tab = selected_tab

active_tab = st.session_state.active_tab


# ======================== Содержимое вкладок ========================

if active_tab == "🏠 Карточки":
    st.markdown(f"### Найдено: **{len(f)}** из {len(df)} ЖК")

    if len(f) == 0:
        st.info("Нет объектов под текущие фильтры. Попробуй сбросить фильтры.")
    else:
        page_size = 10
        total_pages = max(1, (len(f) + page_size - 1) // page_size)

        if st.session_state.card_page > total_pages:
            st.session_state.card_page = total_pages
        if st.session_state.card_page < 1:
            st.session_state.card_page = 1

        page = st.session_state.card_page
        start = (page - 1) * page_size
        end = start + page_size

        for idx, row in f.iloc[start:end].iterrows():
            render_card(row, key_prefix=f"card_{idx}")

        st.markdown("---")
        nav1, nav2, nav3 = st.columns([1, 2, 1])

        with nav1:
            if st.button("← Предыдущая", disabled=(page <= 1), use_container_width=True):
                st.session_state.card_page = page - 1
                st.rerun()

        with nav3:
            if st.button("Следующая →", disabled=(page >= total_pages), use_container_width=True):
                st.session_state.card_page = page + 1
                st.rerun()

        with nav2:
            st.markdown(
                f"<div style='text-align:center; padding-top:8px;'>"
                f"Страница <b>{page}</b> из <b>{total_pages}</b>"
                f"</div>",
                unsafe_allow_html=True,
            )


elif active_tab == "🗺 Карта":
    geo = f.dropna(subset=["lat", "lon"]) if "lat" in f.columns else pd.DataFrame()
    if len(geo) == 0:
        st.warning("Нет объектов с координатами под текущие фильтры")
    else:
        st.caption("💡 Кликни по маркеру — откроется карточка этого ЖК во вкладке «📄 Карточка»")

        center = [geo["lat"].mean(), geo["lon"].mean()]
        m = folium.Map(location=center, zoom_start=10, tiles="OpenStreetMap")
        cluster = MarkerCluster().add_to(m)

        colors = {
            "business": "green", "comfort": "blue", "elite": "red",
            "эконом": "gray", "комфорт": "blue",
            "бизнес": "green", "элит": "red",
        }

        for _, r in geo.iterrows():
            cls = str(r.get("complex_class", "")).lower()
            color = colors.get(cls, "purple")

            popup_html = (
                f"<b>{r.get('complex_name', '—')}</b><br>"
                f"{fmt_price(r)}<br>"
                f"{fmt_metro(r)}<br>"
                f"{r.get('rooms', '—')} комн · {r.get('total_area', '—')} м²"
            )

            folium.CircleMarker(
                [r["lat"], r["lon"]],
                radius=8,
                color=color,
                fill=True,
                fill_opacity=0.9,
                weight=2,
                tooltip=r.get("complex_name", "ЖК"),
                popup=folium.Popup(popup_html, max_width=280),
            ).add_to(cluster)

        map_data = st_folium(
            m,
            height=650,
            use_container_width=True,
            key="map_main",
            returned_objects=["last_object_clicked"],
        )

        if map_data and map_data.get("last_object_clicked"):
            clicked = map_data["last_object_clicked"]
            clat, clon = clicked.get("lat"), clicked.get("lng")
            if clat is not None and clon is not None:
                match = geo[
                    (geo["lat"].round(6) == round(clat, 6)) &
                    (geo["lon"].round(6) == round(clon, 6))
                ]
                if len(match) > 0:
                    new_id = str(match.iloc[0]["id"])
                    if st.session_state.selected_zhk != new_id:
                        # Открываем карточку и переключаем вкладку
                        st.session_state.selected_zhk = new_id
                        st.session_state.active_tab = "📄 Карточка"
                        st.rerun()


elif active_tab == "📄 Карточка":
    sel_id = st.session_state.selected_zhk
    if not sel_id:
        st.info(
            "Кликни по маркеру на карте или нажми «📄 Открыть подробную карточку» в списке — "
            "здесь появится подробная информация о ЖК."
        )
    else:
        row_match = df[df["id"].astype(str) == str(sel_id)]
        if len(row_match) == 0:
            st.warning("ЖК не найден. Возможно, фильтры его скрыли.")
        else:
            row = row_match.iloc[0]
            st.markdown(f"## {row.get('complex_name', '—')}")
            render_card(row, key_prefix=f"full_{sel_id}", full=True, show_open_button=False)
            st.markdown("---")
            if st.button("← Вернуться к списку"):
                st.session_state.selected_zhk = None
                st.session_state.active_tab = "🏠 Карточки"
                st.rerun()


elif active_tab == "❤ Избранное":
    fav_ids = st.session_state.favorites
    if not fav_ids:
        st.info("Ты ещё не добавил ни одной новостройки в избранное.")
    else:
        fav_df = df[df["id"].astype(str).isin(fav_ids)]
        st.markdown(f"### В избранном: **{len(fav_df)}** ЖК")

        if st.button("🗑 Очистить избранное"):
            st.session_state.favorites = set()
            st.rerun()

        for idx, row in fav_df.iterrows():
            render_card(row, key_prefix=f"fav_{idx}")


elif active_tab == "📊 Аналитика":
    if len(f) == 0:
        st.warning("Нет данных для аналитики")
    else:
        if "price_mln" in f.columns and f["price_mln"].notna().any():
            st.subheader("Распределение цен, млн ₽")
            st.plotly_chart(
                px.histogram(f.dropna(subset=["price_mln"]), x="price_mln", nbins=30),
                use_container_width=True,
            )

        if "complex_class" in f.columns and "price_per_sqm" in f.columns and f["price_per_sqm"].notna().any():
            box_df = f.dropna(subset=["price_per_sqm", "complex_class"])
            if len(box_df) > 0:
                st.subheader("Цена за м² по классу")
                st.plotly_chart(
                    px.box(box_df, x="complex_class", y="price_per_sqm"),
                    use_container_width=True,
                )

        if "city" in f.columns and "price_per_sqm" in f.columns:
            grp = (
                f.dropna(subset=["city", "price_per_sqm"])
                .groupby("city")["price_per_sqm"]
                .mean()
                .sort_values(ascending=False)
                .head(15)
            )
            if len(grp) > 0:
                st.subheader("Средняя цена за м² по городам")
                st.bar_chart(grp)

        if "developer" in f.columns and f["developer"].notna().any():
            st.subheader("Топ застройщиков по числу ЖК")
            st.bar_chart(f["developer"].value_counts().head(15))

        if "completion_year" in f.columns and f["completion_year"].notna().any():
            st.subheader("Распределение по годам сдачи")
            st.bar_chart(f["completion_year"].value_counts().sort_index())