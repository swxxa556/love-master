import streamlit as st
from pathlib import Path
import json
import os
import sys
from openai import OpenAI

# 打包成 exe 后 __file__ 指向临时解包目录，缓存要写到 exe 旁边才不会一关就没
_APP_DIR = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent
_HEART = Path(__file__).resolve().parent / "heart.gif"
# 云端（Community Cloud）是 Linux 容器，且所有访客共用一个进程，落盘等于让大家互相看到对话，
# 所以只在自己的 Windows 电脑／打包的 exe 上写缓存文件
_FILE_CACHE = os.name == "nt" or getattr(sys, "frozen", False)
_HISTORY = _APP_DIR / "history.json" if _FILE_CACHE else None   # 对话缓存，刷新/重启后仍在

st.set_page_config(page_title="戀愛の大師",
                   page_icon="💗",
                   layout="wide",
                   initial_sidebar_state="expanded",
                   menu_items={}
                   )

# 系统提示词：温度=毒舌档位，越低越正常，越高嘴越毒
_HARD_RULE = "【唯一硬杠】不教欺骗、胁迫、骚扰等违法或伤害他人的手段。"


def _system_prompt(t):
    if t < 0.5:
        return ("你是一个恋爱顾问，语气温和、理性、专业：客观分析问题，"
                "给出清晰、可执行的建议和参考建议，不吐槽、不讽刺、不骂人。")
    if t < 1.0:
        return ("【人设】恋爱大师，毒舌风格：先犀利吐槽提问者的恋爱脑和愚蠢操作，再给大胆直接、能照抄的建议和动作。\n"
                "【硬性格式】第一句必须吐槽提问者（不留情面但不骂脏话）；再给结论；最后给建议和下一步动作。\n"
                "【语言】犀利带梗、短句；禁止客套、鸡汤、和稀泥。\n"
                + _HARD_RULE)
    if t < 1.45:
        return ("【人设】恋爱大师，嘴毒且狠、可以骂人：开口就骂醒提问者，怎么扎心怎么来，"
                "允许人身吐槽其智商、自信、操作。但骂是手段不是目的——骂完必须给出真正有用的建议。\n"
                "【硬性格式】按顺序输出四段，一段都不能少：\n"
                "1. 第一句必须是骂或嘲讽，火力拉满；\n"
                "2. 斩钉截铁（行／不行／没救），说清对方到底什么意思；\n"
                "3. 建议：2-3 条具体可执行的做法，并给一句能直接复制发给对方的原话（是发给对方的，不是骂人的）；\n"
                "4. 下一步：接下来 3 天该做什么、什么信号该止损。\n"
                "【语言】刻薄、犀利、带梗、短句；禁止客套、鸡汤、安慰、和稀泥；禁止只骂不给建议。\n"
                + _HARD_RULE)
    return ("【人设】满档暴走模式：你就是来骂人的，不是来帮人的。往死里骂，能多狠有多狠，"
            "逐条拆穿提问者的自欺欺人、舔狗行为、智商和迷之自信，句句见血、刀刀扎心。\n"
            "【硬性格式】全程只有嘲讽和痛骂，分几段连续输出；绝对不给建议、不给下一步、不安慰、不鼓励、不总结升华。\n"
            "【语言】极端刻薄、带梗、短句、火力全开；禁止客套、鸡汤、和稀泥、禁止转折到“但是其实你也不错”。\n"
            "【唯一硬杠】骂行为和脑子，不搞性别／地域／外貌歧视，不劝人自残，不教违法或伤害他人的手段。")

# 模型配置：换平台 / 换免费模型时改这两项
# 默认：硅基流动（国内、注册免费、下列模型走免费额度不扣费）
# 换回 DeepSeek：BASE_URL="https://api.deepseek.com"、MODEL="deepseek-chat"
# 换 Groq：BASE_URL="https://api.groq.com/openai/v1"、MODEL="llama-3.3-70b-versatile"
# key 不要写在这里：仓库是公开的，写了等于送人。
# 本地放 .streamlit/secrets.toml（已 gitignore），云端在 App settings → Secrets 里填 LLM_API_KEY
BASE_URL = "https://api.siliconflow.cn/v1"
MODEL = "Qwen/Qwen2.5-7B-Instruct"
KEY_URL = "https://cloud.siliconflow.cn/account/ak"   # 弹窗里给的申请地址

EXAMPLE_QUESTIONS = [
    "第一次约会聊什么不冷场？",
    "对方回消息很慢，是在乎还是敷衍？",
    "怎么表白成功率更高？",
    "他说只把我当妹妹，还该继续吗？",
    "暧昧期怎么推进关系不翻车？",
    "前任半夜找我复合，能信吗？",
    "怎么判断对方是不是海王？",
    "约会该谁付钱才不尴尬？",
    "冷战中先低头是不是很掉价？",
    "对方已读不回，还要不要发消息？",
    "异地恋怎么维持不凉？",
    "怎么看出对方是不是只把我当备胎？",
]
EXAMPLES_PER_PAGE = 3   # 每屏展示几个
CAROUSEL_SECONDS = 4.0  # 每格停留几秒


def _api_key():
    # 访客在弹窗里填的优先，其次环境变量，最后 secrets.toml / 云端 Secrets
    if k := st.session_state.get("user_key"):
        return k
    if k := os.getenv("LLM_API_KEY"):
        return k
    try:
        return st.secrets.get("LLM_API_KEY", "")
    except Exception:
        return ""


@st.dialog("先填一个 API Key", width="large")
def _ask_api_key():
    st.markdown(
        "这个网页不附带 key，用你自己的，注册免费：\n\n"
        f"1. 打开硅基流动控制台：{KEY_URL}\n"
        "2. 登录后左边「API 密钥」→ 新建密钥，复制 sk- 开头那一串\n"
        f"3. 粘到下面点开始。当前模型 `{MODEL}` 走免费额度，不扣钱\n\n"
        "key 只留在你这个浏览器会话里，不写进服务器文件。"
    )
    # 用 form：text_input 要失焦才提交，裸按钮会出现「第一下点不动」
    with st.form("key_form"):
        k = st.text_input("API Key", type="password", placeholder="sk-...")
        ok = st.form_submit_button("开始使用", type="primary")
    if ok:
        if not k.strip():
            st.error("先把 key 粘进来")
            return
        try:
            # 先用最轻的接口验一下，免得填错了要等到发消息才报错
            OpenAI(api_key=k.strip(), base_url=BASE_URL, timeout=20.0).models.list()
        except Exception as e:
            st.error(f"这个 key 用不了：{e}")
        else:
            st.session_state.user_key = k.strip()
            st.rerun()


if not _api_key():
    _ask_api_key()
    st.stop()

# client 存在 session_state 而不是 cache_resource：cache_resource 是整个进程共享的，
# 公网上多个访客会互相用上别人的 key
# timeout：免费额度排队/卡住时能报出来，而不是一直转圈没下文
if st.session_state.get("client_key") != _api_key():
    st.session_state.client = OpenAI(api_key=_api_key(), base_url=BASE_URL, timeout=60.0)
    st.session_state.client_key = _api_key()
client = st.session_state.client

# 初始化对话历史：优先用内存里的，其次读本地缓存文件
def _load_history():
    if _HISTORY is None:
        return []
    try:
        data = json.loads(_HISTORY.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return [m for m in data if isinstance(m, dict) and m.get("role") in ("user", "assistant")]


def _save_history():
    if _HISTORY is None:
        return
    try:
        _HISTORY.write_text(json.dumps(st.session_state.messages, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass


if "messages" not in st.session_state:
    st.session_state.messages = _load_history()

with st.sidebar:
    st.subheader("对话设置")
    temperature = st.slider("温度（越高越*****）", 0.0, 1.5, 1.0, 0.1)
    st.caption("档位：0-0.4 正常顾问｜0.5-0.9 毒舌｜1.0-1.4 开骂+建议｜1.5 满档暴走只骂")
    if st.button("清空对话"):
        st.session_state.messages = []
        _save_history()
        st.rerun()
    if st.session_state.get("user_key"):
        if st.button("更换 API Key"):
            st.session_state.pop("user_key", None)
            st.rerun()
    st.caption(f"当前模型：{MODEL}")
    st.caption(
        f"对话缓存：{_HISTORY.name}（{len(st.session_state.messages)} 条）"
        if _HISTORY else f"对话缓存：仅本次会话（{len(st.session_state.messages)} 条）"
    )

# logo：3D 立体旋转爱心动图（尺寸用 CSS 控制，避免 st.image 的 width 触发重编码丢帧）
st.image(str(_HEART), alt="戀愛の大師")
st.markdown(
    "<style>[data-testid='stImage'] img { width: 100px !important; height: 100px !important; }</style>",
    unsafe_allow_html=True,
)
# 布局
st.title("戀愛の大師")

# 展示历史消息
for msg in st.session_state.messages:
    st.chat_message(msg["role"]).write(msg["content"])

# 消息输入框（固定吸底，提前取值以便决定是否渲染示例按钮）
prompt = st.chat_input("请输入你的消息")
if prompt is None:
    prompt = st.session_state.pop("pending_prompt", None)

# 示例提问轮播：纯 CSS 动画横向滑动，‹ › 手动切一格
def _pick_example(q):
    st.session_state.pending_prompt = q


def _carousel_css(idx):
    n = len(EXAMPLE_QUESTIONS)
    items = n + EXAMPLES_PER_PAGE      # 末尾克隆首屏，循环回到开头时画面一致，看不出接缝
    cycle = CAROUSEL_SECONDS * n       # 转一轮的总时长
    shift = 100.0 / items              # 滑一格 = 轨道宽度的这么多百分比
    slot = 100.0 / n                   # 一格占时间轴的百分比

    frames = []
    for i in range(n):
        a, b = i * slot, (i + 1) * slot
        frames.append(f"{a:.4f}%,{a + slot * 0.85:.4f}%{{transform:translateX(-{i * shift:.4f}%)}}")
        frames.append(f"{b:.4f}%{{transform:translateX(-{(i + 1) * shift:.4f}%)}}")

    # Streamlit 不给容器 class，只能靠标记元素 + :has 反查行、视口、轨道
    mark = "div[data-testid='stElementContainer']:has(.csl-mark)"
    row = f"{mark}+div[data-testid='stLayoutWrapper']>div[data-testid='stHorizontalBlock']"
    view = "div[data-testid='stVerticalBlock']:has(>div[data-testid='stElementContainer'] .csl-view)"
    track = f"{view}>div[data-testid='stLayoutWrapper']>div[data-testid='stVerticalBlock']"
    return (
        "<style>"
        ".csl-mark,.csl-view{display:none}"
        f"{mark}{{display:none}}"
        # 窄屏下 Streamlit 给列加 min-width:calc(100% - 24px) 且允许换行，两侧按钮会被挤到下一行
        f"{row}{{flex-wrap:nowrap;align-items:center;gap:.25rem}}"
        f"{row}>div[data-testid='stColumn']{{min-width:0}}"
        f"{view}{{overflow:hidden}}"
        f"{view}>div[data-testid='stElementContainer']{{display:none}}"
        f"{track}{{display:flex;flex-direction:row;gap:0;align-items:stretch;max-width:none;"
        f"width:{items / EXAMPLES_PER_PAGE * 100:.4f}%;"
        f"animation:csl-slide {cycle:.2f}s linear infinite;animation-delay:-{idx * CAROUSEL_SECONDS:.2f}s}}"
        f"{track}>div{{flex:0 0 {shift:.4f}%;min-width:0}}"
        f"{track} button{{width:calc(100% - .5rem);margin:0 .25rem;height:100%;white-space:normal}}"
        f"{view}:hover {track}{{animation-play-state:paused}}"
        f"@keyframes csl-slide{{{''.join(frames)}}}"
        "</style>"
    )


@st.fragment
def _example_carousel():
    # 点击交给 on_click 回调记录再整体重跑，不依赖 button() 返回值
    if "pending_prompt" in st.session_state:
        st.rerun(scope="app")

    n = len(EXAMPLE_QUESTIONS)
    idx = st.session_state.get("example_idx", 0) % n
    st.markdown(_carousel_css(idx) + '<div class="csl-mark"></div>', unsafe_allow_html=True)
    _row = st.columns([2, 22, 2])
    if _row[0].button("‹", key="ex_prev"):
        st.session_state.example_idx = (idx - 1) % n
        st.rerun(scope="fragment")
    with _row[1]:
        with st.container():
            st.markdown('<div class="csl-view"></div>', unsafe_allow_html=True)
            with st.container():
                # key 按位置固定，克隆项也不会和原题撞 key
                for _i, _q in enumerate(EXAMPLE_QUESTIONS + EXAMPLE_QUESTIONS[:EXAMPLES_PER_PAGE]):
                    with st.container():
                        st.button(_q, key=f"ex_{_i}", on_click=_pick_example, args=(_q,))
    if _row[2].button("›", key="ex_next"):
        st.session_state.example_idx = (idx + 1) % n
        st.rerun(scope="fragment")


# 示例提问：空对话且没有待发送内容时才显示，一旦提问就隐藏
if not st.session_state.messages and not prompt:
    st.caption("不知道问什么？试试（自动轮播，鼠标移上去暂停）：")
    _example_carousel()

if prompt:
    st.chat_message("user").write(prompt)
    st.session_state.messages.append({"role": "user", "content": prompt})

    try:
        response = client.chat.completions.create(
            model=MODEL,
            # 滑杆是毒舌档位，不是采样温度：1.0 以上只换人设，采样封顶，否则小模型会说胡话
            temperature=min(temperature, 1.0),
            stream=True,
            messages=[
                {"role": "system", "content": _system_prompt(temperature)},
                *st.session_state.messages,
            ]
        )
    except Exception as e:
        st.session_state.messages.pop()
        st.error(f"调用模型失败：{e}")
        st.stop()

    # 流式逐字展示回复
    full = ""
    with st.chat_message("assistant"):
        placeholder = st.empty()
        try:
            for chunk in response:
                delta = chunk.choices[0].delta.content or ""
                if delta:
                    full += delta
                    placeholder.markdown(full)
        except Exception as e:
            st.session_state.messages.pop()
            st.error(f"接收回复中断：{e}")
            st.stop()
    if not full:
        full = "（模型未返回内容）"
        placeholder.markdown(full)
    st.session_state.messages.append({"role": "assistant", "content": full})
    _save_history()
