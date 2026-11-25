"""Словесник — ИИ-помощник по русскому языку и литературе."""
import random
from urllib.parse import quote

import requests
import streamlit as st

import prompts as P
from llm import LLMError, generate
from topics import LITERATURE, NO_PORTRAIT, RUSSIAN

st.set_page_config(page_title="Словесник — ИИ-помощник", page_icon="📖", layout="wide")

ss = st.session_state
ss.setdefault("stats", {"tests": 0, "correct": 0, "total": 0})


# ---------- общие компоненты ----------

def ask(prompt, system, **kw):
    try:
        with st.spinner("ИИ думает…"):
            return generate(prompt, system=system, **kw)
    except LLMError as e:
        st.error(str(e))
        return None


def shuffle_quiz(quiz):
    """Перемешиваем варианты, чтобы верный ответ не стоял на одном месте."""
    for q in quiz.get("questions", []):
        right = q["options"][q["answer"]]
        random.shuffle(q["options"])
        q["answer"] = q["options"].index(right)
    return quiz


def grade_quiz(key):
    quiz = ss[key]
    score = sum(ss.get(f"{key}_q{i}") == q["options"][q["answer"]] for i, q in enumerate(quiz["questions"]))
    ss[key + "_done"] = True
    ss[key + "_score"] = score
    ss.stats["tests"] += 1
    ss.stats["correct"] += score
    ss.stats["total"] += len(quiz["questions"])


def render_quiz(key):
    quiz = ss.get(key)
    if not quiz:
        return
    st.subheader(quiz.get("title", "Тест"))
    done = ss.get(key + "_done", False)
    with st.form(key + "_form"):
        for i, q in enumerate(quiz["questions"]):
            st.markdown(f"**{i + 1}. {q['question']}**")
            st.radio("Ответ", q["options"], index=None, key=f"{key}_q{i}",
                     label_visibility="collapsed", disabled=done)
            if done:
                chosen = ss.get(f"{key}_q{i}")
                right = q["options"][q["answer"]]
                if chosen == right:
                    st.success(f"Верно. {q.get('explanation', '')}")
                else:
                    st.error(f"Неверно. Правильный ответ: **{right}**. {q.get('explanation', '')}")
        st.form_submit_button("Проверить", type="primary", disabled=done, on_click=grade_quiz, args=(key,))
    if done:
        n = len(quiz["questions"])
        score = ss[key + "_score"]
        pct = round(100 * score / n)
        st.metric("Результат", f"{score} из {n}", f"{pct}%")
        if pct >= 90:
            st.balloons()


def clear_answers(key):
    """Сбрасывает ответы и результаты прошлого теста, не трогая настройки."""
    for k in [k for k in ss if k.startswith((key + "_q", key + "_a", key + "_done", key + "_score", key + "_result"))]:
        del ss[k]


def set_quiz(key, quiz):
    clear_answers(key)
    ss[key] = shuffle_quiz(quiz)


def render_tasks(key, system):
    data = ss.get(key)
    if not data:
        return
    st.subheader(data.get("title", "Практические задания"))
    with st.form(key + "_form"):
        for i, t in enumerate(data["tasks"]):
            st.markdown(f"**{i + 1}.** {t['task']}")
            st.text_input("Ваш ответ", key=f"{key}_a{i}", label_visibility="collapsed",
                          placeholder="Ваш ответ…")
            with st.expander("Подсказка"):
                st.write(t.get("hint", "—"))
        submitted = st.form_submit_button("Проверить с помощью ИИ", type="primary")
    if submitted:
        answers = [ss.get(f"{key}_a{i}", "") for i in range(len(data["tasks"]))]
        res = ask(P.check_tasks(data["tasks"], answers), system, as_json=True, temperature=0.2)
        if res:
            ss[key + "_result"] = res
            ok = sum(bool(r.get("correct")) for r in res.get("results", []))
            ss.stats["tests"] += 1
            ss.stats["correct"] += ok
            ss.stats["total"] += len(data["tasks"])
    res = ss.get(key + "_result")
    if res:
        results = res.get("results", [])
        ok = sum(bool(r.get("correct")) for r in results)
        st.metric("Результат", f"{ok} из {len(data['tasks'])}")
        for i, (t, r) in enumerate(zip(data["tasks"], results), 1):
            box = st.success if r.get("correct") else st.error
            box(f"**{i}.** {r.get('comment', '')}\n\nЭталон: {t['answer']}")
        st.info(res.get("summary", ""))


@st.cache_data(show_spinner=False, ttl=86400)
def portrait(name):
    try:
        r = requests.get("https://ru.wikipedia.org/w/api.php", timeout=10, params={
            "action": "query", "format": "json", "generator": "search", "gsrsearch": name + " писатель",
            "gsrlimit": 1, "prop": "pageimages", "piprop": "thumbnail", "pithumbsize": 300},
            headers={"User-Agent": "SlovesnikBot/1.0 (student project)"})
        pages = r.json().get("query", {}).get("pages", {})
        for p in pages.values():
            return p.get("thumbnail", {}).get("source")
    except Exception:
        return None


# ---------- разделы ----------

def page_russian():
    st.header("📘 Русский язык")
    c1, c2, c3 = st.columns([2, 3, 1])
    section = c1.selectbox("Раздел", list(RUSSIAN))
    topic = c2.selectbox("Тема", RUSSIAN[section])
    level = c3.selectbox("Уровень", P.LEVELS, index=1)

    tab_theory, tab_quiz, tab_tasks = st.tabs(["📖 Теория", "✅ Тест", "✍️ Практические задания"])
    with tab_theory:
        if st.button("Объяснить тему", type="primary", key="ru_theory_btn"):
            text = ask(P.ru_theory(section, topic, level), P.RU_TEACHER)
            if text:
                ss.ru_theory = text
        if ss.get("ru_theory"):
            st.markdown(ss.ru_theory)
    with tab_quiz:
        n = st.slider("Количество вопросов", 3, 15, 5, key="ru_quiz_n")
        if st.button("Сгенерировать тест", type="primary", key="ru_quiz_btn"):
            quiz = ask(P.ru_quiz(section, topic, level, n), P.RU_TEACHER, as_json=True, temperature=0.4)
            if quiz:
                set_quiz("ru_quiz", quiz)
        render_quiz("ru_quiz")
    with tab_tasks:
        n = st.slider("Количество заданий", 3, 10, 5, key="ru_tasks_n")
        if st.button("Сгенерировать задания", type="primary", key="ru_tasks_btn"):
            data = ask(P.ru_tasks(section, topic, level, n), P.RU_TEACHER, as_json=True, temperature=0.4)
            if data:
                clear_answers("ru_tasks")
                ss.ru_tasks = data
        render_tasks("ru_tasks", P.RU_TEACHER)


def page_literature():
    st.header("📚 Литература")
    c1, c2, c3 = st.columns(3)
    period = c1.selectbox("Период", list(LITERATURE))
    author = c2.selectbox("Автор / раздел", list(LITERATURE[period]))
    work = c3.selectbox("Произведение / тема", LITERATURE[period][author])
    is_theory = author == "Теория литературы"

    left, right = st.columns([1, 3])
    with left:
        if author not in NO_PORTRAIT:
            img = portrait(author)
            if img:
                st.image(img, caption=author, width=260)
        if not is_theory and st.button("🎨 Сгенерировать иллюстрацию"):
            desc = ask(P.illustration_prompt(author, work), None, temperature=0.9)
            if desc:
                ss.lit_img = (work, f"https://image.pollinations.ai/prompt/{quote(desc.strip())}"
                                    f"?width=768&height=512&nologo=true&seed={random.randint(1, 10**6)}")
        if ss.get("lit_img") and ss.lit_img[0] == work:
            st.markdown(f'<img src="{ss.lit_img[1]}" style="width:100%;border-radius:8px" '
                        f'alt="Иллюстрация генерируется… (лимит бесплатного сервиса — 1 картинка в 45 сек)">',
                        unsafe_allow_html=True)
            st.caption("Иллюстрация создана ИИ (Pollinations)")

    with right:
        actions = P.LIT_THEORY_ACTIONS if is_theory else P.LIT_ACTIONS
        tab_info, tab_quiz = st.tabs(["📖 Материалы", "✅ Тест"])
        with tab_info:
            action = st.radio("Что нужно?", list(actions), horizontal=True)
            if st.button("Получить", type="primary", key="lit_info_btn"):
                text = ask(actions[action].format(author=author, work=work), P.LIT_TEACHER)
                if text:
                    ss.lit_info = text
            if ss.get("lit_info"):
                st.markdown(ss.lit_info)
        with tab_quiz:
            q1, q2 = st.columns(2)
            n = q1.slider("Количество вопросов", 3, 15, 5, key="lit_quiz_n")
            level = q2.selectbox("Уровень", P.LEVELS, index=1, key="lit_level")
            if st.button("Сгенерировать тест", type="primary", key="lit_quiz_btn"):
                quiz = ask(P.lit_quiz(author, work, n, level), P.LIT_TEACHER, as_json=True, temperature=0.5)
                if quiz:
                    set_quiz("lit_quiz", quiz)
            render_quiz("lit_quiz")


def page_chat():
    st.header("💬 Чат-помощник")
    subject = st.radio("Предмет", ["Русский язык", "Литература"], horizontal=True)
    key = "chat_ru" if subject == "Русский язык" else "chat_lit"
    system = P.RU_TEACHER if subject == "Русский язык" else P.LIT_TEACHER
    ss.setdefault(key, [])

    if st.button("Очистить чат"):
        ss[key] = []
    if not ss[key]:
        hint = ("Например: «Как пишется „не“ с причастиями?» или «Проверь пунктуацию в предложении…»"
                if key == "chat_ru" else "Например: «В чём смысл финала „Грозы“?» или «Сравни Онегина и Печорина»")
        st.caption(hint)
    for m in ss[key]:
        with st.chat_message("user" if m["role"] == "user" else "assistant"):
            st.markdown(m["text"])

    if q := st.chat_input("Задайте вопрос…"):
        with st.chat_message("user"):
            st.markdown(q)
        answer = ask(q, system, history=ss[key][-20:])
        if answer:
            ss[key] += [{"role": "user", "text": q}, {"role": "model", "text": answer}]
            with st.chat_message("assistant"):
                st.markdown(answer)


def page_about():
    st.header("ℹ️ О проекте")
    st.markdown("""
**Словесник** — веб-приложение с искусственным интеллектом для изучения русского языка и литературы в вузе.

**Возможности**
- **Русский язык:** объяснение тем, автоматическая генерация тестов и практических заданий, проверка ответов ИИ.
- **Литература:** краткое содержание, анализ, характеристика героев, планы сочинений, вопросы к семинару, тесты, портреты авторов и ИИ-иллюстрации.
- **Чат-помощник:** отдельные чаты по русскому языку и литературе.

**Технологии:** Python, Streamlit, Google Gemini API, Wikipedia API, Pollinations.ai.
""")
    st.caption(f"Тем по русскому языку: {sum(map(len, RUSSIAN.values()))} · "
               f"Произведений и тем по литературе: {sum(len(w) for p in LITERATURE.values() for w in p.values())}")


# ---------- навигация ----------

PAGES = {"📘 Русский язык": page_russian, "📚 Литература": page_literature,
         "💬 Чат-помощник": page_chat, "ℹ️ О проекте": page_about}

with st.sidebar:
    st.title("📖 Словесник")
    st.caption("ИИ-помощник по русскому языку и литературе")
    page = st.radio("Раздел", list(PAGES), label_visibility="collapsed")
    st.divider()
    stats_box = st.container()

PAGES[page]()

# прогресс рисуем после страницы, чтобы учесть только что проверенный тест
with stats_box:
    s = ss.stats
    st.markdown("**Ваш прогресс**")
    st.write(f"Пройдено тестов: **{s['tests']}**")
    if s["total"]:
        st.progress(s["correct"] / s["total"], text=f"Верных ответов: {s['correct']} из {s['total']}")
