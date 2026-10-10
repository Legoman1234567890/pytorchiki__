import re
import time
import hashlib
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
    transition: box-shadow 0.15s ease, border-color 0.15s ease;
    animation: zhkFadeIn 0.35s ease-out both;
}
@keyframes zhkFadeIn {
    from { opacity: 0; transform: translateY(6px); }
    to   { opacity: 1; transform: translateY(0); }
}
.zhk-card-link {
    text-decoration: none !important;
    color: inherit !important;
    display: block;
}
.zhk-card-link:hover .zhk-card {
    box-shadow: 0 4px 12px rgba(0,0,0,0.08);
    border-color: #cfd8ff;
    cursor: pointer;
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

/* Плашка "Фильтры применены" */
.filters-applied {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 10px 16px;
    margin: 8px 0 16px 0;
    border-radius: 10px;
    background: linear-gradient(90deg, #e7f6ec 0%, #eef3ff 100%);
    border-left: 4px solid #0d7a3f;
    color: #1a1a1a;
    font-size: 15px;
    animation: appliedPulse 1.2s ease-out;
}
@keyframes appliedPulse {
    0%   { background-color: #c7f0d5; transform: scale(1.01); }
    100% { background-color: transparent; transform: scale(1); }
}
.filters-applied b { color: #0d7a3f; }

/* Плашка "Сброшено" */
.filters-reset {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 10px 16px;
    margin: 8px 0 16px 0;
    border-radius: 10px;
    background: linear-gradient(90deg, #fff4e5 0%, #ffe9d6 100%);
    border-left: 4px solid #b05a00;
    color: #1a1a1a;
    font-size: 15px;
    animation: appliedPulse 1.2s ease-out;
}

/* Скрываем встроенную стрелку sidebar — фильтры в expander */
@media (max-width: 768px) {
    [data-testid="stSidebarCollapsedControl"],
    [data-testid="collapsedControl"] {
        display: none !important;
    }
    section[data-testid="stSidebar"] {
        display: none !important;
    }
}
</style>
""", unsafe_allow_html=True)


# ======================== ЗАГРУЗКА ДАННЫХ ========================

_CORPUS_PATTERN = re.compile(
    r"\s*[\(\[\-–—,:]?\s*"
    r"(корпус|корп\.?|литер|секц(ия|\.)?|блок|строение|стр\.?|этап|очередь)"
    r"\s*[№#]?\s*[\w\d\-–—/]*\s*[\)\]]?\s*$",
    re.IGNORECASE,
)


def _strip_corpus(name: str) -> str:
    if not isinstance(name, str):
        return ""
    s = name.strip()
    for _ in range(3):
        new_s = _CORPUS_PATTERN.sub("", s).strip(" ,-–—")
        if new_s == s:
            break
        s = new_s
    return s


def _extract_zhk_name(row) -> str:
    for col in ("zhk_name", "residential_complex", "project_name", "jk_name", "complex_full_name"):
        val = row.get(col)
        if isinstance(val, str) and val.strip() and val.strip().lower() not in ("nan", "none"):
            return val.strip()

    raw = row.get("complex_name", "")
    cleaned = _strip_corpus(raw) if isinstance(raw, str) else ""

    if cleaned:
        return cleaned

    dev = row.get("developer")
    city = row.get("city")
    parts = [p for p in (dev, city) if isinstance(p, str) and p.strip()]
    if parts:
        return " · ".join(parts)

    return "ЖК без названия"


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

    df["zhk_name"] = df.apply(_extract_zhk_name, axis=1)

    return df


df = load()

if df.empty:
    st.error("Файл production_data_merged.csv пуст или не найден.")
    st.stop()


# ======================== SESSION STATE ========================

if "favorites" not in st.session_state:
    st.session_state.favorites = set()
if "selected_zhk" not in st.session_state:
    st.session_state.selected_zhk = None
if "card_page" not in st.session_state:
    st.session_state.card_page = 1
if "active_tab" not in st.session_state:
    st.session_state.active_tab = "🏠 Карточки"
if "last_clicked_marker_id" not in st.session_state:
    st.session_state.last_clicked_marker_id = None
if "filters_version" not in st.session_state:
    st.session_state.filters_version = 0
# Хэш предыдущего состояния фильтров + флаг сброса
if "prev_filters_hash" not in st.session_state:
    st.session_state.prev_filters_hash = None
if "filters_just_reset" not in st.session_state:
    st.session_state.filters_just_reset = False


def reset_filters():
    for k in list(st.session_state.keys()):
        if k.startswith("flt_"):
            del st.session_state[k]
    st.session_state.filters_version += 1
    st.session_state.card_page = 1
    # Флаг для отображения плашки «Фильтры сброшены»
    st.session_state.filters_just_reset = True
    # Сбрасываем сохранённый хэш, чтобы плашка «применены» не путалась
    st.session_state.prev_filters_hash = None


def toggle_fav(zhk_id):
    if zhk_id in st.session_state.favorites:
        st.session_state.favorites.remove(zhk_id)
    else:
        st.session_state.favorites.add(zhk_id)


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


# ======================== ОБРАБОТКА КЛИКА ПО КАРТОЧКЕ ========================
qp_zhk = st.query_params.get("zhk_id")
if qp_zhk:
    st.query_params.clear()
    st.session_state.selected_zhk = str(qp_zhk)
    st.session_state.active_tab = "📄 Карточка"


# ======================== ЗНАЧЕНИЯ ПО УМОЛЧАНИЮ ========================
v = st.session_state.filters_version

default_sources = (
    sorted(df["source"].dropna().unique().tolist())
    if "source" in df.columns else []
)
default_price_to = (
    float(np.nanmax(df["price_mln"]))
    if "price_mln" in df and df["price_mln"].notna().any() else 0.0
)
default_floor_to = (
    int(np.nanmax(df["floor"]))
    if "floor" in df and df["floor"].notna().any() else 100
)
default_metro_to = METRO_MAX_REAL


# ======================== ФИЛЬТРЫ ========================
def render_filters():
    st.button(
        "♻️ Сбросить фильтры",
        on_click=reset_filters,
        use_container_width=True,
        key=f"reset_btn_{v}",
    )

    if "city" in df.columns:
        cities = sorted(df["city"].dropna().unique().tolist())
        sel_cities = st.multiselect("Город", cities, default=[], key=f"flt_cities_{v}")
    else:
        sel_cities = []

    if "source" in df.columns:
        sources = sorted(df["source"].dropna().unique().tolist())
        sel_sources = st.multiselect("Источник данных", sources, default=default_sources, key=f"flt_sources_{v}")
    else:
        sel_sources = []

    if "developer" in df.columns:
        developers = sorted(df["developer"].dropna().unique().tolist())
        sel_devs = st.multiselect("Застройщик", developers, default=[], key=f"flt_devs_{v}")
    else:
        sel_devs = []

    if "complex_class" in df.columns:
        classes = sorted(df["complex_class"].dropna().unique().tolist())
        sel_classes = st.multiselect("Класс ЖК", classes, default=[], key=f"flt_classes_{v}")
    else:
        sel_classes = []

    st.markdown("**Цена, млн ₽**")
    col_p1, col_p2 = st.columns(2)
    price_from = col_p1.number_input(
        "от", min_value=0.0, value=0.0, step=0.5,
        key=f"flt_price_from_{v}", label_visibility="collapsed",
    )
    price_to = col_p2.number_input(
        "до", min_value=0.0, value=default_price_to, step=0.5,
        key=f"flt_price_to_{v}", label_visibility="collapsed",
    )
    st.caption("от / до")

    st.markdown("**Этаж**")
    col_f1, col_f2 = st.columns(2)
    floor_from = col_f1.number_input(
        "от ", min_value=0, value=0, step=1,
        key=f"flt_floor_from_{v}", label_visibility="collapsed",
    )
    floor_to = col_f2.number_input(
        "до ", min_value=0, value=default_floor_to, step=1,
        key=f"flt_floor_to_{v}", label_visibility="collapsed",
    )
    st.caption("от / до")

    st.markdown("**До метро, мин**")
    if "metro_distance_min" in df.columns and df["metro_distance_min"].notna().any():
        col_m1, col_m2 = st.columns(2)
        metro_from = col_m1.number_input(
            "от  ", min_value=0, value=0, step=1,
            key=f"flt_metro_from_{v}", label_visibility="collapsed",
        )
        metro_to = col_m2.number_input(
            "до  ", min_value=0, value=default_metro_to, step=1,
            key=f"flt_metro_to_{v}", label_visibility="collapsed",
        )
        st.caption("от / до")
        st.caption("⚠️ При сужении диапазона объекты без метро скрываются")
    else:
        metro_from, metro_to = 0, 999

    if "rooms" in df.columns:
        rooms_all = sorted(df["rooms"].dropna().unique().tolist())
        sel_rooms = st.multiselect("Комнат", rooms_all, default=[], key=f"flt_rooms_{v}")
    else:
        sel_rooms = []

    area_from = st.number_input(
        "Площадь от, м²", min_value=0.0, value=0.0, step=1.0,
        key=f"flt_area_from_{v}",
    )

    only_mortgage = st.checkbox(
        "Только со льготной ипотекой", value=False, key=f"flt_mortgage_{v}",
    )

    return {
        "sel_cities": sel_cities,
        "sel_sources": sel_sources,
        "sel_devs": sel_devs,
        "sel_classes": sel_classes,
        "sel_rooms": sel_rooms,
        "price_from": price_from,
        "price_to": price_to,
        "floor_from": floor_from,
        "floor_to": floor_to,
        "metro_from": metro_from,
        "metro_to": metro_to,
        "area_from": area_from,
        "only_mortgage": only_mortgage,
    }


with st.expander("🔍 Показать фильтры", expanded=False):
    filters = render_filters()

sel_cities = filters["sel_cities"]
sel_sources = filters["sel_sources"]
sel_devs = filters["sel_devs"]
sel_classes = filters["sel_classes"]
sel_rooms = filters["sel_rooms"]
price_from = filters["price_from"]
price_to = filters["price_to"]
floor_from = filters["floor_from"]
floor_to = filters["floor_to"]
metro_from = filters["metro_from"]
metro_to = filters["metro_to"]
area_from = filters["area_from"]
only_mortgage = filters["only_mortgage"]


# ======================== ХЭШ СОСТОЯНИЯ ФИЛЬТРОВ ========================
# Формируем строку из всех значений фильтров и хэшируем.
# Если хэш изменился — фильтры были пересчитаны.
filters_signature = "|".join([
    ",".join(map(str, sorted(sel_cities))),
    ",".join(map(str, sorted(sel_sources))),
    ",".join(map(str, sorted(sel_devs))),
    ",".join(map(str, sorted(sel_classes))),
    ",".join(map(str, sorted(map(str, sel_rooms)))),
    str(price_from), str(price_to),
    str(floor_from), str(floor_to),
    str(metro_from), str(metro_to),
    str(area_from), str(only_mortgage),
])
current_hash = hashlib.md5(filters_signature.encode("utf-8")).hexdigest()

filters_changed = (
    st.session_state.prev_filters_hash is not None
    and st.session_state.prev_filters_hash != current_hash
)
filters_reset_just_now = st.session_state.filters_just_reset

# Обновляем сохранённый хэш и сбрасываем флаг
st.session_state.prev_filters_hash = current_hash
st.session_state.filters_just_reset = False


# ======================== ФИЛЬТРАЦИЯ ========================
# Спиннер показывается, только если фильтры поменялись — визуальная обратная связь
if filters_changed or filters_reset_just_now:
    with st.spinner("Применяем фильтры…"):
        time.sleep(0.25)  # короткая пауза, чтобы спиннер успел появиться

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


# ======================== ПЛАШКА "ФИЛЬТРЫ ПРИМЕНЕНЫ" ========================
if filters_reset_just_now:
    st.markdown(
        f"""
        <div class="filters-reset">
            <span style="font-size:20px;">♻️</span>
            <span>Фильтры <b>сброшены</b>. Показано <b>{len(f)}</b> из {len(df)} ЖК.</span>
        </div>
        """,
        unsafe_allow_html=True,
    )
elif filters_changed:
    st.markdown(
        f"""
        <div class="filters-applied">
            <span style="font-size:20px;">✅</span>
            <span>Фильтры <b>применены</b>. Найдено <b>{len(f)}</b> из {len(df)} ЖК.</span>
        </div>
        """,
        unsafe_allow_html=True,
    )


# ======================== RENDER CARD ========================
def render_card(row, key_prefix, full=False):
    zhk_id = str(row["id"])
    is_fav = zhk_id in st.session_state.favorites

    col_left, col_right = st.columns([6, 1])

    with col_left:
        card_html = f"""
        <div class="zhk-card">
            <div class="zhk-title">{row.get('zhk_name', 'ЖК без названия')}</div>
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
        """

        if not full:
            st.markdown(
                f'<a href="?zhk_id={zhk_id}" target="_self" class="zhk-card-link">{card_html}</a>',
                unsafe_allow_html=True,
            )
        else:
            st.markdown(card_html, unsafe_allow_html=True)

        if pd.notna(row.get("url")):
            st.markdown(f"[🔗 Открыть на {row.get('source', 'сайте')}]({row['url']})")

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

    with col_right:
        label = "💔 Убрать" if is_fav else "❤ В избранное"
        if st.button(label, key=f"{key_prefix}_fav_{zhk_id}"):
            toggle_fav(zhk_id)
            st.rerun()


# ======================== НАВИГАЦИЯ ========================
TAB_LABELS = ["🏠 Карточки", "🗺 Карта", "📄 Карточка", "❤ Избранное", "📊 Аналитика"]

if st.session_state.active_tab not in TAB_LABELS:
    st.session_state.active_tab = "🏠 Карточки"

active_index = TAB_LABELS.index(st.session_state.active_tab)

selected_tab = st.radio(
    "Навигация",
    TAB_LABELS,
    index=active_index,
    horizontal=True,
    label_visibility="collapsed",
)

if selected_tab != st.session_state.active_tab:
    st.session_state.active_tab = selected_tab

active_tab = st.session_state.active_tab


# ======================== TAB: КАРТОЧКИ ========================
if active_tab == "🏠 Карточки":
    st.markdown(f"### Найдено: **{len(f)}** из {len(df)} ЖК")
    st.caption("💡 Кликни по карточке, чтобы открыть подробную информацию")

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


# ======================== TAB: КАРТА ========================
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

        geo = geo.copy()
        geo["lat_r"] = geo["lat"].round(6)
        geo["lon_r"] = geo["lon"].round(6)

        for _, r in geo.iterrows():
            cls = str(r.get("complex_class", "")).lower()
            color = colors.get(cls, "purple")

            popup_html = (
                f"<b>{r.get('zhk_name', '—')}</b><br>"
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
                tooltip=r.get("zhk_name", "ЖК"),
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
                    (geo["lat_r"] == round(clat, 6)) &
                    (geo["lon_r"] == round(clon, 6))
                ]
                if len(match) > 0:
                    new_id = str(match.iloc[0]["id"])
                    click_signature = f"{new_id}_{clat}_{clon}"
                    if st.session_state.last_clicked_marker_id != click_signature:
                        st.session_state.last_clicked_marker_id = click_signature
                        st.session_state.selected_zhk = new_id
                        st.session_state.active_tab = "📄 Карточка"
                        st.rerun()


# ======================== TAB: КАРТОЧКА ========================
elif active_tab == "📄 Карточка":
    sel_id = st.session_state.selected_zhk
    if not sel_id:
        st.info(
            "Кликни по карточке в списке или по маркеру на карте — "
            "здесь появится подробная информация о ЖК."
        )
    else:
        row_match = df[df["id"].astype(str) == str(sel_id)]
        if len(row_match) == 0:
            st.warning("ЖК не найден. Возможно, фильтры его скрыли.")
        else:
            row = row_match.iloc[0]
            st.markdown(f"## {row.get('zhk_name', '—')}")
            render_card(row, key_prefix=f"full_{sel_id}", full=True)
            st.markdown("---")
            if st.button("← Вернуться к списку"):
                st.session_state.selected_zhk = None
                st.session_state.active_tab = "🏠 Карточки"
                st.rerun()


# ======================== TAB: ИЗБРАННОЕ ========================
elif active_tab == "❤ Избранное":
    fav_ids = st.session_state.favorites
    if not fav_ids:
        st.info("Ты ещё не добавил ни одной новостройки в избранное.")
    else:
        fav_df = df[df["id"].astype(str).isin(fav_ids)]
        st.markdown(f"### В избранном: **{len(fav_df)}** ЖК")
        st.caption("💡 Кликни по карточке, чтобы открыть подробную информацию")

        if st.button("🗑 Очистить избранное"):
            st.session_state.favorites = set()
            st.rerun()

        for idx, row in fav_df.iterrows():
            render_card(row, key_prefix=f"fav_{idx}")


# ======================== TAB: АНАЛИТИКА ========================
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

        if "developer" in f.columns and f["
