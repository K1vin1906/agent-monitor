#!/usr/bin/env python3
"""Agent Monitor - 异构 Agent 实时监控面板"""

import asyncio
import codecs
import json
import os
import time
from pathlib import Path
from textual.app import App
from textual.screen import Screen
from textual.widgets import Header, Footer, Static, RichLog, Label, Input, Button
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.reactive import reactive
from textual.timer import Timer
from rich.text import Text
from rich.panel import Panel
from rich.table import Table

SOCKET_PATH = os.environ.get("AGENT_MONITOR_SOCKET", "/tmp/agent-monitor.sock")
# MCP Server 目录：优先环境变量，否则取 monitor 同级目录
_default_mcp_dir = Path(__file__).resolve().parent.parent / "mcp-multi-model"
MCP_SERVER_DIR = Path(os.environ.get("MCP_MULTI_MODEL_DIR", str(_default_mcp_dir)))

SPINNERS = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]

# 常见 LLM 提供商及其 API Key 环境变量名
COMMON_PROVIDERS = [
    ("OpenAI", "OPENAI_API_KEY"),
    ("Anthropic / Claude", "ANTHROPIC_API_KEY"),
    ("Google Gemini", "GEMINI_API_KEY"),
    ("DeepSeek", "DEEPSEEK_API_KEY"),
    ("Moonshot / Kimi", "KIMI_API_KEY"),
    ("通义千问", "DASHSCOPE_API_KEY"),
    ("百度文心", "QIANFAN_API_KEY"),
    ("零一万物", "YI_API_KEY"),
    ("智谱", "ZHIPU_API_KEY"),
    ("Groq", "GROQ_API_KEY"),
    ("Mistral", "MISTRAL_API_KEY"),
    ("Cohere", "COHERE_API_KEY"),
    ("xAI / Grok", "XAI_API_KEY"),
]

# 自动配色轮转
_AGENT_COLORS = ["cyan", "green", "magenta", "yellow", "blue", "red", "#ff8700", "#af87ff", "#5fd7ff", "#87d787"]

def _build_agent_config() -> dict:
    """从 config.yaml 动态生成 agent 配置，如果读不到则用默认"""
    try:
        import yaml
    except ImportError:
        yaml = None

    config_path = MCP_SERVER_DIR / "config.yaml"
    if yaml and config_path.exists():
        cfg = yaml.safe_load(config_path.read_text())
        models = cfg.get("models", {})
        result = {}
        for i, (key, mcfg) in enumerate(models.items()):
            result[key] = {
                "label": mcfg.get("name", key),
                "color": _AGENT_COLORS[i % len(_AGENT_COLORS)],
                "order": i,
            }
        if result:
            return result

    # fallback
    return {
        "deepseek": {"label": "DeepSeek", "color": "green", "order": 0},
        "gemini": {"label": "Gemini", "color": "cyan", "order": 1},
        "kimi": {"label": "Kimi", "color": "magenta", "order": 2},
    }

AGENT_CONFIG = _build_agent_config()


# ── 设置页面 ──

def load_env():
    """读取 MCP Server 的 .env 文件"""
    env = {}
    env_path = MCP_SERVER_DIR / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if "=" in line and not line.startswith("#"):
                key, _, val = line.partition("=")
                env[key.strip()] = val.strip().strip('"')
    return env


def save_env(env: dict):
    """保存到 MCP Server 的 .env 文件"""
    env_path = MCP_SERVER_DIR / ".env"
    lines = [f"{k}={v}" for k, v in env.items() if v]
    env_path.write_text("\n".join(lines) + "\n")


def load_config():
    """读取 MCP Server 的 config.yaml"""
    try:
        import yaml
    except ImportError:
        return None
    config_path = MCP_SERVER_DIR / "config.yaml"
    if config_path.exists():
        return yaml.safe_load(config_path.read_text())
    return None


def mask_key(key: str) -> str:
    if not key or len(key) < 10:
        return key or ""
    return key[:6] + "•" * 8 + key[-4:]


class HelpScreen(Screen):
    CSS = """
    HelpScreen { align: center middle; }
    #help-box {
        width: 50;
        max-height: 70%;
        border: thick $primary;
        background: $surface;
        padding: 1 2;
    }
    .help-title { text-align: center; text-style: bold; padding: 1 0; }
    .help-row { padding: 0 0 0 2; }
    """
    BINDINGS = [("escape", "dismiss", "Close"), ("h", "dismiss", "Close")]

    def compose(self):
        with Vertical(id="help-box"):
            yield Label("Keyboard Shortcuts", classes="help-title")
            yield Label("[bold cyan]q[/]    Quit", classes="help-row")
            yield Label("[bold cyan]c[/]    Clear all panels", classes="help-row")
            yield Label("[bold cyan]d[/]    Toggle Compare / Unified view", classes="help-row")
            yield Label("[bold cyan]s[/]    API Key Settings", classes="help-row")
            yield Label("[bold cyan]h[/]    This help screen", classes="help-row")
            yield Label("[bold cyan]Esc[/]  Close current dialog", classes="help-row")
            yield Label("")
            yield Label("[dim]Agent Monitor v3.0  ·  github.com/...[/]", classes="help-row")

    def action_dismiss(self):
        self.app.pop_screen()


class SettingsScreen(Screen):
    CSS = """
    SettingsScreen {
        align: center middle;
    }
    #settings-container {
        width: 76;
        max-height: 85%;
        border: thick $primary;
        background: $surface;
        padding: 1 2;
    }
    .settings-title {
        text-align: center;
        text-style: bold;
        color: $text;
        padding: 1 0;
    }
    .section-title {
        text-style: bold;
        color: $accent;
        padding: 1 0 0 0;
    }
    .key-label {
        padding: 1 0 0 0;
        color: $text-muted;
    }
    Input {
        margin: 0 0 1 0;
    }
    #btn-row {
        height: 3;
        align: center middle;
        padding: 1 0;
    }
    Button {
        margin: 0 2;
    }
    """

    BINDINGS = [("escape", "cancel", "Cancel")]

    def __init__(self):
        super().__init__()
        self.env = load_env()
        self.config = load_config()
        self.model_keys = []
        # config.yaml 中已注册的模型
        if self.config and "models" in self.config:
            self.model_keys = list(self.config["models"].keys())
        # 收集 config.yaml 中已被使用的 env_var，用于去重
        self._configured_env_vars: set[str] = set()
        for key in self.model_keys:
            cfg = self.config["models"][key]
            env_var = cfg.get("api_key_env", "")
            if env_var:
                self._configured_env_vars.add(env_var)
        # 筛选出 config.yaml 中未覆盖的常见提供商
        self._extra_providers = [
            (name, env_var)
            for name, env_var in COMMON_PROVIDERS
            if env_var not in self._configured_env_vars
        ]

    def compose(self):
        with VerticalScroll(id="settings-container"):
            yield Label("⚙  API Key Settings", classes="settings-title")
            yield Label(f"[dim]Config: {MCP_SERVER_DIR}[/]", classes="key-label")

            # ── 区域 1: 已配置模型 ──
            if self.model_keys:
                yield Label("── Configured Models ──", classes="section-title")
                for key in self.model_keys:
                    cfg = self.config["models"][key]
                    env_var = cfg.get("api_key_env", "")
                    current = self.env.get(env_var, "")
                    status = (
                        f"[green]✓ Set[/] [dim]{mask_key(current)}[/]"
                        if current
                        else "[red]✗ Not set[/]"
                    )
                    yield Label(
                        f"[bold]{cfg.get('name', key)}[/]  ({env_var})  {status}",
                        classes="key-label",
                    )
                    yield Input(
                        placeholder=f"Enter {env_var} (leave empty to keep current)",
                        id=f"input-{key}",
                        password=True,
                    )
            else:
                yield Label("[red]config.yaml not found or empty[/]")

            # ── 区域 2: 其他常见提供商 ──
            if self._extra_providers:
                yield Label("── Other API Keys ──", classes="section-title")
                for name, env_var in self._extra_providers:
                    current = self.env.get(env_var, "")
                    status = (
                        f"[green]✓ Set[/] [dim]{mask_key(current)}[/]"
                        if current
                        else "[dim]Not configured[/]"
                    )
                    yield Label(
                        f"[bold]{name}[/]  ({env_var})  {status}",
                        classes="key-label",
                    )
                    safe_id = env_var.lower().replace("_", "-")
                    yield Input(
                        placeholder=f"Enter {env_var} (leave empty to skip)",
                        id=f"input-{safe_id}",
                        password=True,
                    )

            with Horizontal(id="btn-row"):
                yield Button("Save", variant="success", id="btn-save")
                yield Button("Cancel", variant="default", id="btn-cancel")

    def on_button_pressed(self, event: Button.Pressed):
        if event.button.id == "btn-save":
            self._save()
        elif event.button.id == "btn-cancel":
            self.app.pop_screen()

    def _save(self):
        changed = False

        # 1. 保存已配置模型的 key
        for key in self.model_keys:
            cfg = self.config["models"][key]
            env_var = cfg.get("api_key_env", "")
            try:
                inp = self.query_one(f"#input-{key}", Input)
            except Exception:
                continue
            val = inp.value.strip()
            if val:
                self.env[env_var] = val
                changed = True

        # 2. 保存其他常见提供商的 key
        for _name, env_var in self._extra_providers:
            safe_id = env_var.lower().replace("_", "-")
            try:
                inp = self.query_one(f"#input-{safe_id}", Input)
            except Exception:
                continue
            val = inp.value.strip()
            if val:
                self.env[env_var] = val
                changed = True

        if changed:
            save_env(self.env)
            self.app.notify("Saved! Restart MCP Server to apply.", severity="information")
        else:
            self.app.notify("No changes.", severity="warning")
        self.app.pop_screen()

    def action_cancel(self):
        self.app.pop_screen()


# ── 主界面组件 ──

class AgentCard(Static):
    """单个 Agent 的状态卡片"""
    status = reactive("idle")
    model = reactive("")
    total_tokens = reactive(0)
    total_calls = reactive(0)
    total_cost = reactive(0.0)
    last_activity = reactive("")
    last_activity_ts = reactive(0.0)
    spin_frame = reactive(0)

    def __init__(self, agent_key: str, agent_cfg: dict | None = None, **kwargs):
        super().__init__(**kwargs)
        cfg = agent_cfg or AGENT_CONFIG.get(agent_key, {"label": agent_key, "color": "white", "order": 99})
        self.agent_key = agent_key
        self.agent_label = cfg["label"]
        self.color = cfg["color"]
        self._spinner_timer: Timer | None = None

    def on_mount(self):
        self._spinner_timer = self.set_interval(0.1, self._tick_spinner)

    def _tick_spinner(self):
        if self.status == "working":
            self.spin_frame = (self.spin_frame + 1) % len(SPINNERS)

    def render(self):
        if self.status == "working":
            icon = f"[bold yellow]{SPINNERS[self.spin_frame]}[/]"
            state = f"[bold yellow]Working[/]"
        elif self.status == "done":
            icon = "[bold green]●[/]"
            state = "[bold green]Done[/]"
        elif self.status == "error":
            icon = "[bold red]●[/]"
            state = "[bold red]Error[/]"
        else:
            icon = f"[dim {self.color}]◆[/]"
            state = f"[dim]Standby[/]"

        title = f"[bold {self.color}]{self.agent_label}[/]"
        model_str = f"[dim]{self.model}[/]" if self.model else "[dim]—[/]"
        calls_str = f"[dim]Calls:[/] {self.total_calls}"
        tokens_str = f"[dim]Tokens:[/] {self.total_tokens:,}"
        cost_str = f"[dim]Cost:[/] ${self.total_cost:.4f}" if self.total_cost > 0 else ""
        if self.last_activity_ts > 0:
            delta = time.time() - self.last_activity_ts
            if delta < 60:
                time_str = f"[dim]{int(delta)}s ago[/]"
            elif delta < 3600:
                time_str = f"[dim]{int(delta // 60)}m ago[/]"
            else:
                time_str = f"[dim]{self.last_activity}[/]"
        else:
            time_str = ""

        lines = [
            f" {icon} {title}  {state}",
            f"   {model_str}",
            f"   {calls_str}  {tokens_str}  {cost_str}  {time_str}",
        ]
        return Text.from_markup("\n".join(lines))


class ConnectionStatus(Static):
    """连接状态指示器"""
    connected = reactive(False)

    def render(self):
        if self.connected:
            return Text.from_markup("[bold green]● Connected[/] [dim]to MCP Server[/]")
        else:
            return Text.from_markup("[bold red]● Disconnected[/] [dim]waiting for MCP Server...[/]")


class AgentMonitorApp(App):
    CSS = """
    Screen {
        layout: grid;
        grid-size: 1 5;
        grid-rows: auto 5 1fr 8 auto;
        background: $surface;
    }

    #connection-bar {
        height: 1;
        padding: 0 2;
        background: $surface-darken-1;
    }

    #status-bar {
        height: 5;
        padding: 0 1;
    }

    .agent-card {
        width: 1fr;
        min-width: 25;
        height: 100%;
        border: round $primary-darken-2;
        padding: 0 1;
        margin: 0 1;
    }
    .agent-card:focus {
        border: round $primary;
    }

    #main-panels {
        height: 1fr;
    }

    .panel-box {
        width: 1fr;
        border: solid $primary-darken-2;
        margin: 0 0 0 0;
    }
    #prompt-box {
        border: solid $secondary 40%;
    }
    #response-box {
        border: solid $success 40%;
    }

    .panel-title {
        dock: top;
        background: $surface-darken-1;
        padding: 0 1;
        text-style: bold;
        color: $text;
    }

    #event-section {
        height: 8;
        border: solid $warning 30%;
        margin: 0 0 0 0;
    }
    #event-section .panel-title {
        background: $surface-darken-1;
    }

    #compare-panels {
        height: 1fr;
        display: none;
    }
    .compare-col {
        width: 1fr;
        border: solid $primary-darken-2;
        margin: 0 0 0 0;
    }
    .compare-title {
        dock: top;
        background: $surface-darken-1;
        padding: 0 1;
        text-style: bold;
    }

    RichLog {
        scrollbar-size: 1 1;
    }
    """

    TITLE = "Agent Monitor"
    SUB_TITLE = "异构 Agent 实时监控"
    BINDINGS = [
        ("q", "quit", "Quit"),
        ("c", "clear_all", "Clear"),
        ("d", "toggle_compare", "Compare"),
        ("h", "show_help", "Help"),
        ("s", "open_settings", "Settings"),
    ]

    def compose(self):
        yield Header()
        yield ConnectionStatus(id="connection-bar")
        with Horizontal(id="status-bar"):
            for key, cfg in AGENT_CONFIG.items():
                yield AgentCard(key, agent_cfg=cfg, id=f"{key}-card", classes="agent-card")
        with Horizontal(id="main-panels"):
            with Vertical(id="prompt-box", classes="panel-box"):
                yield Label("[bold $secondary]  Prompt [dim](Claude → Sub-Agent)[/]", classes="panel-title")
                yield RichLog(id="prompt-log", wrap=True, max_lines=200)
            with Vertical(id="response-box", classes="panel-box"):
                yield Label("[bold $success]  Response [dim](Sub-Agent Output)[/]", classes="panel-title")
                yield RichLog(id="response-log", wrap=True, max_lines=500)
        with Horizontal(id="compare-panels"):
            for key, cfg in AGENT_CONFIG.items():
                with Vertical(id=f"compare-{key}", classes="compare-col"):
                    yield Label(f"[bold {cfg['color']}]  {cfg['label']}[/]", classes="compare-title")
                    yield RichLog(id=f"compare-log-{key}", wrap=True, max_lines=500)
        with Vertical(id="event-section"):
            yield Label("[bold $warning]  Event Log", classes="panel-title")
            yield RichLog(id="events", wrap=True, max_lines=100)
        yield Footer()

    def on_mount(self):
        self._stream_buffers: dict[str, str] = {}
        self._compare_mode = False
        self.connect_task = asyncio.create_task(self.connect_to_socket())
        self.set_interval(0.3, self._flush_streams)

    def _write_to_response(self, agent: str, content):
        """双写：同时写入统一 log 和对比 log，切换视图时不丢内容"""
        self.query_one("#response-log", RichLog).write(content)
        try:
            self.query_one(f"#compare-log-{agent}", RichLog).write(content)
        except Exception:
            pass

    def _flush_streams(self):
        """定期刷新流式 buffer 到 response_log"""
        if not self._stream_buffers:
            return
        for key in list(self._stream_buffers):
            text = self._stream_buffers[key]
            if text:
                self._write_to_response(key, Text(text))
                self._stream_buffers[key] = ""

    async def connect_to_socket(self):
        """连接 UDS 并持续读取事件"""
        conn_status = self.query_one("#connection-bar", ConnectionStatus)
        events_log = self.query_one("#events", RichLog)

        while True:
            try:
                reader, _ = await asyncio.open_unix_connection(SOCKET_PATH)
                conn_status.connected = True
                events_log.write(Text.from_markup(
                    f"[green][{self._ts()}] Connected to MCP Server[/]"
                ))

                buffer = ""
                decoder = codecs.getincrementaldecoder("utf-8")()
                while True:
                    data = await reader.read(4096)
                    if not data:
                        conn_status.connected = False
                        events_log.write(Text.from_markup(
                            f"[yellow][{self._ts()}] Disconnected. Reconnecting...[/]"
                        ))
                        break
                    buffer += decoder.decode(data, final=False)
                    while "\n" in buffer:
                        line, buffer = buffer.split("\n", 1)
                        if line.strip():
                            try:
                                event = json.loads(line)
                                self.handle_event(event)
                            except json.JSONDecodeError:
                                pass
            except (ConnectionRefusedError, FileNotFoundError):
                conn_status.connected = False
            except Exception as e:
                conn_status.connected = False
                events_log.write(Text.from_markup(f"[red][{self._ts()}] Error: {e}[/]"))

            await asyncio.sleep(2)

    def _ts(self, ms_timestamp=None):
        if ms_timestamp:
            return time.strftime("%H:%M:%S", time.localtime(ms_timestamp / 1000))
        return time.strftime("%H:%M:%S")

    def handle_event(self, event):
        """处理单个事件"""
        etype = event.get("type", "")
        agent = event.get("agent", "unknown")
        ts = self._ts(event.get("timestamp"))

        card_id = f"#{agent}-card"
        prompt_log = self.query_one("#prompt-log", RichLog)
        response_log = self.query_one("#response-log", RichLog)
        events_log = self.query_one("#events", RichLog)

        try:
            card = self.query_one(card_id, AgentCard)
        except Exception:
            card = None

        if card:
            color = card.color
            label = card.agent_label.upper()
        else:
            # 未注册 agent 的 fallback
            color = "white"
            label = agent.upper()

        if etype == "AGENT_START":
            if card:
                card.status = "working"
                card.model = event.get("model", "")
                card.total_calls += 1
                card.last_activity = ts
                card.last_activity_ts = time.time()

            prompt_text = event.get("prompt", "")
            sys_prompt = event.get("systemPrompt", "")

            prompt_log.write(Text.from_markup(
                f"\n[bold {color}]{'━' * 3} [{ts}] Claude → {label} {'━' * 20}[/]"
            ))
            if sys_prompt:
                prompt_log.write(Text.from_markup(f"  [dim italic]System: {sys_prompt}[/]"))
            prompt_log.write(Text.from_markup(f"  {prompt_text}"))

            self._write_to_response(agent, Text.from_markup(
                f"\n[bold {color}]{'━' * 3} [{ts}] {label} {'━' * 20}[/]"
            ))

            events_log.write(Text.from_markup(
                f"[{color}][{ts}] ▶ {label} started[/] [dim]({event.get('model', '')})[/]"
            ))

        elif etype == "AGENT_END":
            tokens = event.get("tokens", {})
            cost_usd = event.get("cost_usd", 0)
            if card:
                card.status = "done"
                card.total_tokens += tokens.get("total", 0)
                card.total_cost += cost_usd
                card.last_activity = ts
                card.last_activity_ts = time.time()

            tok_in = tokens.get("prompt", 0)
            tok_out = tokens.get("completion", 0)
            tok_total = tokens.get("total", 0)
            duration_ms = event.get("duration_ms", 0)
            dur_str = f" · {duration_ms / 1000:.1f}s" if duration_ms else ""
            cost_str = f" · ${cost_usd:.6f}" if cost_usd > 0 else ""

            streamed = agent in self._stream_buffers
            if streamed:
                remaining = self._stream_buffers.pop(agent, "")
                if remaining:
                    self._write_to_response(agent, Text(remaining))
            else:
                content = event.get("content", "")
                self._write_to_response(agent, content)

            self._write_to_response(agent, Text.from_markup(
                f"  [dim]{tok_in:,} in → {tok_out:,} out = {tok_total:,} tokens{dur_str}{cost_str}[/]"
            ))

            events_log.write(Text.from_markup(
                f"[green][{ts}] ✓ {label} done[/] [dim]({tok_total:,} tokens{dur_str}{cost_str})[/]"
            ))

        elif etype == "AGENT_CHUNK":
            if card:
                card.status = "working"
            delta = event.get("delta", "")
            if delta:
                if agent not in self._stream_buffers:
                    self._stream_buffers[agent] = ""
                self._stream_buffers[agent] += delta

        elif etype == "AGENT_RETRY":
            if card:
                card.last_activity = ts
                card.last_activity_ts = time.time()
            attempt = event.get("attempt", 0)
            status = event.get("status", "")
            wait = event.get("wait", 0)
            events_log.write(Text.from_markup(
                f"[yellow][{ts}] ↻ {label} retry #{attempt}[/] [dim](HTTP {status}, wait {wait / 1000:.0f}s)[/]"
            ))

        elif etype == "AGENT_ERROR":
            if card:
                card.status = "error"
                card.last_activity = ts
                card.last_activity_ts = time.time()
            error = event.get("error", "unknown error")
            err_type = event.get("errType", "")
            type_tag = f" [{err_type}]" if err_type else ""
            events_log.write(Text.from_markup(
                f"[red][{ts}] ✗ {label} error{type_tag}: {error}[/]"
            ))

    def action_toggle_compare(self):
        """切换对比/统一视图"""
        self._compare_mode = not self._compare_mode
        self.query_one("#main-panels").display = not self._compare_mode
        self.query_one("#compare-panels").display = self._compare_mode
        mode = "Compare" if self._compare_mode else "Unified"
        self.sub_title = f"异构 Agent 实时监控 ({mode} View)"
        self.notify(f"Switched to {mode} view", severity="information")

    def action_clear_all(self):
        """清空所有面板"""
        self.query_one("#prompt-log", RichLog).clear()
        self.query_one("#response-log", RichLog).clear()
        self.query_one("#events", RichLog).clear()
        for key in AGENT_CONFIG:
            try:
                self.query_one(f"#compare-log-{key}", RichLog).clear()
            except Exception:
                pass
        self._stream_buffers.clear()
        for key in AGENT_CONFIG:
            card = self.query_one(f"#{key}-card", AgentCard)
            card.status = "idle"
            card.model = ""
            card.total_cost = 0.0
            card.last_activity = ""
            card.last_activity_ts = 0.0

    def action_show_help(self):
        """显示帮助"""
        self.push_screen(HelpScreen())

    def action_open_settings(self):
        """打开设置页面"""
        self.push_screen(SettingsScreen())


if __name__ == "__main__":
    AgentMonitorApp().run()
