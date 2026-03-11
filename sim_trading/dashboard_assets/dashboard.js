    const notificationLimit = Number(window.__SIM_DASHBOARD_CONFIG__?.notificationLimit || 20);
    const I18N = {
      zh: {
        page_title: "模拟交易监控台",
        auto_refresh: "AUTO REFRESH / 5S",
        title: "模拟交易监控台",
        subtitle: "保留现有风格主题，重组为更紧凑的监控布局，并增加策略级视图与中心工作区。",
        lang_label: "界面语言",
        nav: "NAV",
        realized_pnl: "已实现盈亏",
        unrealized_pnl: "未实现盈亏",
        drawdown: "回撤",
        positions: "持仓数",
        market_fetch: "行情抓取",
        signals: "信号",
        health: "健康度",
        execution: "执行",
        validation: "验证",
        risk_gates: "风险门禁",
        ds_decision: "DS 决策状态",
        latest_execution: "最新执行",
        latest_validation: "最新验证",
        latest_signals: "最新信号",
        latest_ds_suggestions: "最新 DS 建议",
        latest_ds_rejection: "最新拒绝原因",
        latest_notifications: "最新通知",
        experiment_runs: "实验评估",
        ops_tabs: "运维标签",
        strategy_control: "策略跟随",
        ops_tab_control: "跟随",
        ops_tab_execution: "执行",
        ops_tab_risk: "风控",
        ops_tab_validation: "验证",
        ops_tab_ds: "DS",
        strategy_follow_enabled: "主仓跟随已启用",
        strategy_follow_disabled: "主仓跟随未启用",
        selected_strategy: "已选策略",
        universe_status: "选币宇宙状态",
        strategy_compare: "策略对比",
        strategy_workspace: "策略工作区",
        strategy_label: "策略",
        strategy_nav_curve: "策略 NAV 曲线",
        market_monitor: "市场监控",
        price_trends: "价格走势",
        positions_summary: "持仓摘要",
        recent_trades: "最近成交",
        recent_events: "最近事件",
        open_positions: "当前持仓",
        loading: "加载中...",
        no_positions: "当前无持仓",
        no_execution: "暂无执行记录",
        no_notifications: "暂无通知记录",
        no_signals: "暂无信号快照",
        no_validation: "暂无验证记录",
        no_ds_decision: "暂无 DS 决策记录",
        no_ds_rejection: "暂无拒绝记录",
        no_ds_applicable: "该策略不使用 DS 规划",
        no_price_history: "暂无价格历史",
        no_universe: "暂无选币宇宙数据",
        no_strategy_compare: "暂无策略对比数据",
        no_trades: "暂无成交记录",
        no_events: "暂无事件记录",
        refresh_failed: "刷新失败: {message}",
        showing_limit: "最多显示 {count} 条",
        snapshot_meta: "快照 {timestamp} | 最近权益入库 {persisted}",
        market_signal_meta: "行情 {market} | 信号 {signal}",
        execution_meta: "{label} | 执行 {timestamp} | 信号 {signal}",
        validation_meta: "{label} | 验证 {timestamp}",
        targets: "目标权重",
        none: "无",
        risk: "风险",
        next: "下一步",
        confidence: "置信度",
        invalidation: "失效条件",
        stop_loss_pct: "止损比例",
        take_profit_pct: "止盈比例",
        market_regime: "市场状态",
        global_risk_mode: "全局风险模式",
        approval_status: "审批状态",
        latest: "最新",
        obs: "观测",
        momentum: "动量",
        ema_slope: "EMA 斜率",
        symbol: "币种",
        qty: "数量",
        avg: "均价",
        mark: "市价",
        upnl: "未实现",
        stop: "止损",
        chart_latest: "最新 {value}",
        chart_range: "区间 {start} -> {end}",
        health_checks: "检查项 {count}",
        mode_normalized_seed_notional: "已规范化持仓",
        mode_synthetic_seed_units: "遗留合成持仓",
        mode_standard_positions: "标准持仓模式",
        mode_normalized_note: "已在 {timestamp} 完成规范化",
        mode_pending_note: "仍有 {count} 个持仓待规范化",
        mode_ready_note: "当前状态无需规范化",
        source_note: "说明: {note}",
        status_ok: "正常",
        status_watch: "观察",
        status_alert: "告警",
        status_running: "运行中",
        status_initialized: "已初始化",
        status_no_change: "无变化",
        status_partial: "部分成交",
        status_canceled: "已取消",
        status_rejected: "已拒绝",
        status_blocked: "已阻断",
        status_approved: "已批准",
        status_consumed: "已消费",
        status_noop: "未执行",
        status_unknown: "未知",
        signal_bullish: "看多",
        signal_bearish: "看空",
        signal_flat: "震荡",
        signal_insufficient: "样本不足",
        signal_unknown: "未知",
        chart_empty: "暂无可绘制数据",
        pending_symbols: "待处理持仓",
        held_assets: "{label} | 持仓资产 {count}",
        fills: "成交",
        rejected: "拒绝",
        canceled: "取消",
        fees: "手续费",
        slippage: "滑点",
        blocked_orders: "已阻断新单",
        kill_switch: "总开关",
        cooldown: "冷却",
        daily_return: "当日收益",
        circuit_breaker: "熔断",
        return_pct: "收益率",
        max_drawdown: "最大回撤",
        current_drawdown: "当前回撤",
        win_rate: "胜率",
        profit_factor: "盈亏比",
        turnover: "换手率",
        risk_triggers: "风险触发",
        recommended_weight: "建议权重",
        longest_losing_streak: "最长连亏",
        consecutive_losses: "连续亏损",
        cycle: "周期",
        enabled: "开启",
        disabled: "关闭",
        active: "生效中",
        inactive: "未触发",
        decision_buy: "买入",
        decision_sell: "卖出",
        decision_hold: "持有",
        ds_mode_disabled: "已禁用",
        ds_mode_shadow: "影子模式",
        ds_mode_approval: "审批模式",
        all_count: "全部",
        filtered_count: "过滤后",
        top120_count: "Top 120",
        top30_count: "Top 30",
        last_refresh: "最新刷新",
        ranking_rule: "排序规则",
        not_initialized: "未初始化",
        overview: "总览",
        gross_exposure: "总暴露",
        cash_ratio: "现金占比",
        largest_position: "最大持仓",
        side: "方向",
        notional: "名义金额",
        realized_pnl_short: "已实现",
        event_risk: "风险",
        event_execution: "执行",
        event_ds: "DS",
        strategy_not_initialized: "策略状态未初始化",
        workspace_loading: "正在加载策略视图...",
        overview_best: "最佳收益",
        strategy_rule: "策略说明",
        updated_at: "更新时间",
        annualized_return: "年化收益",
        annualized_volatility: "年化波动",
        sharpe: "夏普",
        sortino: "索提诺",
        calmar: "卡玛",
        gate_status: "门槛结论",
        status_pass: "通过",
        status_fail: "失败",
      },
      en: {
        page_title: "Sim Trading Dashboard",
        auto_refresh: "AUTO REFRESH / 5S",
        title: "Sim Trading Dashboard",
        subtitle: "Keeps the existing visual direction while restructuring the dashboard around a denser operations layout and strategy-focused workspace.",
        lang_label: "Language",
        nav: "NAV",
        realized_pnl: "Realized PnL",
        unrealized_pnl: "Unrealized PnL",
        drawdown: "Drawdown",
        positions: "Positions",
        market_fetch: "Market Fetch",
        signals: "Signals",
        health: "Health",
        execution: "Execution",
        validation: "Validation",
        risk_gates: "Risk Gates",
        ds_decision: "DS Decision",
        latest_execution: "Latest Execution",
        latest_validation: "Latest Validation",
        latest_signals: "Latest Signals",
        latest_ds_suggestions: "Latest DS Suggestions",
        latest_ds_rejection: "Latest DS Rejection",
        latest_notifications: "Latest Notifications",
        experiment_runs: "Experiment Runs",
        ops_tabs: "Ops Tabs",
        strategy_control: "Strategy Follow",
        ops_tab_control: "Follow",
        ops_tab_execution: "Execution",
        ops_tab_risk: "Risk",
        ops_tab_validation: "Validation",
        ops_tab_ds: "DS",
        strategy_follow_enabled: "Root portfolio follow mode enabled",
        strategy_follow_disabled: "Root portfolio follow mode disabled",
        selected_strategy: "Selected Strategy",
        universe_status: "Universe Status",
        strategy_compare: "Strategy Comparison",
        strategy_workspace: "Strategy Workspace",
        strategy_label: "Strategy",
        strategy_nav_curve: "Strategy NAV Curve",
        market_monitor: "Market Monitor",
        price_trends: "Price Trends",
        positions_summary: "Position Summary",
        recent_trades: "Recent Trades",
        recent_events: "Recent Events",
        open_positions: "Open Positions",
        loading: "Loading...",
        no_positions: "No open positions",
        no_execution: "No execution cycles recorded yet",
        no_notifications: "No notifications logged yet",
        no_signals: "No signal snapshots recorded yet",
        no_validation: "No validation runs recorded yet",
        no_ds_decision: "No DS decision recorded yet",
        no_ds_rejection: "No DS rejection recorded yet",
        no_ds_applicable: "This strategy does not use DS planning",
        no_price_history: "No market-feed history for held assets",
        no_universe: "No universe artifacts recorded yet",
        no_strategy_compare: "No strategy comparison recorded yet",
        no_trades: "No trades recorded yet",
        no_events: "No recent events",
        refresh_failed: "Refresh failed: {message}",
        showing_limit: "Showing up to {count} entries",
        snapshot_meta: "Snapshot {timestamp} | last persisted equity {persisted}",
        market_signal_meta: "Market {market} | Signal run {signal}",
        execution_meta: "{label} | Execution {timestamp} | Signal {signal}",
        validation_meta: "{label} | Validation {timestamp}",
        targets: "Targets",
        none: "none",
        risk: "Risk",
        next: "Next",
        confidence: "Confidence",
        invalidation: "Invalidation",
        stop_loss_pct: "Stop Loss",
        take_profit_pct: "Take Profit",
        market_regime: "Market Regime",
        global_risk_mode: "Global Risk Mode",
        approval_status: "Approval",
        latest: "Latest",
        obs: "obs",
        momentum: "momentum",
        ema_slope: "EMA slope",
        symbol: "Symbol",
        qty: "Qty",
        avg: "Avg",
        mark: "Mark",
        upnl: "uPnL",
        stop: "Stop",
        chart_latest: "Latest {value}",
        chart_range: "Range {start} -> {end}",
        health_checks: "Checks {count}",
        mode_normalized_seed_notional: "Normalized seed-notional mode",
        mode_synthetic_seed_units: "Legacy synthetic seed-unit mode",
        mode_standard_positions: "Standard position mode",
        mode_normalized_note: "Normalized at {timestamp}",
        mode_pending_note: "{count} positions still require normalization",
        mode_ready_note: "No normalization is currently required",
        source_note: "Note: {note}",
        status_ok: "ok",
        status_watch: "watch",
        status_alert: "alert",
        status_running: "running",
        status_initialized: "initialized",
        status_no_change: "no_change",
        status_partial: "partial",
        status_canceled: "canceled",
        status_rejected: "rejected",
        status_blocked: "blocked",
        status_approved: "approved",
        status_consumed: "consumed",
        status_noop: "noop",
        status_unknown: "unknown",
        signal_bullish: "bullish",
        signal_bearish: "bearish",
        signal_flat: "flat",
        signal_insufficient: "insufficient",
        signal_unknown: "unknown",
        chart_empty: "Not enough data to draw a chart",
        pending_symbols: "Pending symbols",
        held_assets: "{label} | Held assets {count}",
        fills: "Fills",
        rejected: "Rejected",
        canceled: "Canceled",
        fees: "Fees",
        slippage: "Slippage",
        blocked_orders: "New Orders Blocked",
        kill_switch: "Kill Switch",
        cooldown: "Cooldown",
        daily_return: "Daily Return",
        circuit_breaker: "Circuit Breaker",
        return_pct: "Return",
        max_drawdown: "Max Drawdown",
        current_drawdown: "Current Drawdown",
        win_rate: "Win Rate",
        profit_factor: "Profit Factor",
        turnover: "Turnover",
        risk_triggers: "Risk Triggers",
        recommended_weight: "Suggested Weight",
        longest_losing_streak: "Longest Losing Streak",
        consecutive_losses: "Consecutive Losses",
        cycle: "cycle",
        enabled: "Enabled",
        disabled: "Disabled",
        active: "Active",
        inactive: "Inactive",
        decision_buy: "buy",
        decision_sell: "sell",
        decision_hold: "hold",
        ds_mode_disabled: "disabled",
        ds_mode_shadow: "shadow",
        ds_mode_approval: "approval",
        all_count: "All",
        filtered_count: "Filtered",
        top120_count: "Top 120",
        top30_count: "Top 30",
        last_refresh: "Last Refresh",
        ranking_rule: "Ranking Rule",
        not_initialized: "Not initialized",
        overview: "Overview",
        gross_exposure: "Gross Exposure",
        cash_ratio: "Cash Ratio",
        largest_position: "Largest Position",
        side: "Side",
        notional: "Notional",
        realized_pnl_short: "Realized",
        event_risk: "Risk",
        event_execution: "Execution",
        event_ds: "DS",
        strategy_not_initialized: "Strategy state is not initialized",
        workspace_loading: "Loading strategy workspace...",
        overview_best: "Best Return",
        strategy_rule: "Strategy Note",
        updated_at: "Updated",
        annualized_return: "Annualized Return",
        annualized_volatility: "Annualized Volatility",
        sharpe: "Sharpe",
        sortino: "Sortino",
        calmar: "Calmar",
        gate_status: "Gate",
        status_pass: "pass",
        status_fail: "fail",
      },
    };

    let currentLang = "zh";
    let activeView = "overview";
    let lastPayload = null;
    let lastHealth = null;
    let resizeTimer = null;
    let activeOpsTab = "control";
    const strategyCache = new Map();

    function t(key, vars = {}) {
      const dict = I18N[currentLang] || I18N.zh;
      let text = dict[key] || I18N.en[key] || key;
      for (const [name, value] of Object.entries(vars)) {
        text = text.replaceAll(`{${name}}`, String(value));
      }
      return text;
    }

    function escapeHtml(value) {
      return String(value ?? "")
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#39;");
    }

    function detectInitialLang() {
      const queryLang = new URLSearchParams(window.location.search).get("lang");
      if (queryLang && I18N[queryLang]) {
        return queryLang;
      }
      const saved = window.localStorage.getItem("sim-trading-lang");
      if (saved && I18N[saved]) {
        return saved;
      }
      return "zh";
    }

    function detectInitialView() {
      const queryView = new URLSearchParams(window.location.search).get("view");
      return queryView || "overview";
    }

    function updateUrlState() {
      const url = new URL(window.location.href);
      url.searchParams.set("lang", currentLang);
      url.searchParams.set("view", activeView);
      window.history.replaceState({}, "", url);
    }

    function money(value) {
      const numeric = Number(value || 0);
      return new Intl.NumberFormat(currentLang === "zh" ? "zh-CN" : "en-US", {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2,
      }).format(numeric);
    }

    function pct(value) {
      const numeric = Number(value || 0);
      return `${(numeric * 100).toFixed(2)}%`;
    }

    function compactTime(value) {
      if (!value) {
        return "n/a";
      }
      return String(value).replace("T", " ").slice(0, 19);
    }

    function statusClass(status) {
      const normalized = String(status || "").toLowerCase();
      if (["alert", "bearish", "rejected", "blocked", "fail"].includes(normalized)) return "status-alert";
      if (["watch", "flat", "insufficient", "partial", "canceled"].includes(normalized)) return "status-watch";
      return "status-ok";
    }

    function hasKey(key) {
      return Object.prototype.hasOwnProperty.call(I18N[currentLang] || {}, key)
        || Object.prototype.hasOwnProperty.call(I18N.en, key);
    }

    function localizedStatus(status) {
      const normalized = String(status || "").toLowerCase();
      const key = `status_${normalized}`;
      return t(hasKey(key) ? key : "status_unknown");
    }

    function localizedSignal(signal) {
      const normalized = String(signal || "").toLowerCase();
      const key = `signal_${normalized}`;
      return t(hasKey(key) ? key : "signal_unknown");
    }

    function localizedDecisionAction(action) {
      const normalized = String(action || "").toLowerCase();
      const key = `decision_${normalized}`;
      return t(hasKey(key) ? key : normalized || t("none"));
    }

    function localizedDsMode(mode) {
      const normalized = String(mode || "").toLowerCase();
      const key = `ds_mode_${normalized}`;
      return t(hasKey(key) ? key : normalized || t("none"));
    }

    function localizedEventCategory(category) {
      const normalized = String(category || "").toLowerCase();
      const key = `event_${normalized}`;
      return t(hasKey(key) ? key : normalized || t("none"));
    }

    function viewLabel(view) {
      return view === "overview" ? t("overview") : String(view || t("overview"));
    }

    function applyI18n() {
      document.title = t("page_title");
      document.documentElement.lang = currentLang === "zh" ? "zh-CN" : "en";
      document.querySelectorAll("[data-i18n]").forEach((node) => {
        node.textContent = t(node.dataset.i18n);
      });
      document.getElementById("lang-select").value = currentLang;
      document.getElementById("notifications-meta").textContent = t("showing_limit", { count: notificationLimit });
    }

    function setLang(lang) {
      currentLang = I18N[lang] ? lang : "zh";
      window.localStorage.setItem("sim-trading-lang", currentLang);
      updateUrlState();
      applyI18n();
      renderAll();
    }

    function drawLineChart(canvas, series, options = {}) {
      const ctx = canvas.getContext("2d");
      const parentWidth = canvas.clientWidth || canvas.width || 320;
      const height = Number(options.height || canvas.height || 140);
      const width = Math.max(160, Math.floor(parentWidth));
      const dpr = window.devicePixelRatio || 1;
      canvas.width = Math.floor(width * dpr);
      canvas.height = Math.floor(height * dpr);
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, width, height);

      if (!Array.isArray(series) || series.length < 2) {
        ctx.fillStyle = "#6e6a63";
        ctx.font = '12px "Noto Sans SC", sans-serif';
        ctx.fillText(t("chart_empty"), 12, Math.floor(height / 2));
        return;
      }

      const values = series.map((item) => Number(item.value));
      const rawMin = Math.min(...values);
      const rawMax = Math.max(...values);
      const paddingValue = rawMax === rawMin ? Math.max(Math.abs(rawMax) * 0.04, 1) : (rawMax - rawMin) * 0.08;
      const min = rawMin - paddingValue;
      const max = rawMax + paddingValue;
      const left = 12;
      const right = 12;
      const top = 12;
      const bottom = 18;
      const plotWidth = width - left - right;
      const plotHeight = height - top - bottom;
      const color = options.color || "#1d6b6f";

      ctx.strokeStyle = "rgba(30, 35, 48, 0.08)";
      ctx.lineWidth = 1;
      for (let i = 0; i < 3; i += 1) {
        const y = top + (plotHeight / 2) * i;
        ctx.beginPath();
        ctx.moveTo(left, y);
        ctx.lineTo(width - right, y);
        ctx.stroke();
      }

      const points = series.map((item, index) => {
        const x = left + (plotWidth * index) / Math.max(series.length - 1, 1);
        const y = top + ((max - Number(item.value)) / Math.max(max - min, 1e-9)) * plotHeight;
        return { x, y };
      });

      if (options.fill) {
        const gradient = ctx.createLinearGradient(0, top, 0, height);
        gradient.addColorStop(0, `${color}33`);
        gradient.addColorStop(1, `${color}00`);
        ctx.beginPath();
        ctx.moveTo(points[0].x, height - bottom);
        points.forEach((point) => ctx.lineTo(point.x, point.y));
        ctx.lineTo(points[points.length - 1].x, height - bottom);
        ctx.closePath();
        ctx.fillStyle = gradient;
        ctx.fill();
      }

      ctx.beginPath();
      points.forEach((point, index) => {
        if (index === 0) {
          ctx.moveTo(point.x, point.y);
        } else {
          ctx.lineTo(point.x, point.y);
        }
      });
      ctx.strokeStyle = color;
      ctx.lineWidth = 2;
      ctx.lineJoin = "round";
      ctx.lineCap = "round";
      ctx.stroke();

      const lastPoint = points[points.length - 1];
      ctx.beginPath();
      ctx.arc(lastPoint.x, lastPoint.y, 3, 0, Math.PI * 2);
      ctx.fillStyle = color;
      ctx.fill();
    }

    function renderMode(snapshot) {
      const badge = document.getElementById("mode-badge");
      const note = document.getElementById("mode-note");
      const source = document.getElementById("mode-source");
      const modeKey = `mode_${snapshot.position_mode}`;
      badge.textContent = hasKey(modeKey) ? t(modeKey) : snapshot.position_mode;
      if (snapshot.position_mode_is_normalized) {
        note.textContent = t("mode_normalized_note", { timestamp: compactTime(snapshot.position_normalized_at) });
      } else if (snapshot.position_requires_normalization) {
        note.textContent = t("mode_pending_note", { count: snapshot.pending_normalization_symbols.length });
      } else {
        note.textContent = t("mode_ready_note");
      }
      source.textContent = snapshot.position_mode_source_note
        ? t("source_note", { note: snapshot.position_mode_source_note })
        : "";
    }

    function renderRootCards(snapshot) {
      renderMode(snapshot);
      document.getElementById("nav").textContent = money(snapshot.nav);
      document.getElementById("nav-meta").textContent = compactTime(snapshot.timestamp);
      document.getElementById("realized").textContent = money(snapshot.realized_pnl_total);
      document.getElementById("realized-meta").textContent = snapshot.position_mode_is_normalized
        ? t("mode_normalized_seed_notional")
        : (hasKey(`mode_${snapshot.position_mode}`) ? t(`mode_${snapshot.position_mode}`) : snapshot.position_mode);
      document.getElementById("unrealized").textContent = money(snapshot.unrealized_pnl_total);
      document.getElementById("unrealized-meta").textContent = snapshot.position_requires_normalization
        ? t("mode_pending_note", { count: snapshot.pending_normalization_symbols.length })
        : t("mode_ready_note");
      document.getElementById("drawdown").textContent = pct(snapshot.drawdown_pct);
      document.getElementById("drawdown-meta").textContent = snapshot.breached_stop_losses.length
        ? snapshot.breached_stop_losses.join(", ")
        : "--";
      document.getElementById("positions-count").textContent = String(snapshot.position_count);
      document.getElementById("positions-count-meta").textContent = snapshot.pending_normalization_symbols.length
        ? `${t("pending_symbols")}: ${snapshot.pending_normalization_symbols.join(", ")}`
        : "--";
      document.getElementById("market-fetch").textContent = compactTime(snapshot.latest_market_fetch_at || "n/a");
      document.getElementById("market-fetch-meta").textContent = snapshot.latest_market_fetch?.source
        ? String(snapshot.latest_market_fetch.source)
        : "--";
      document.getElementById("signal-status").textContent = snapshot.latest_signal_summary || "n/a";
      document.getElementById("signal-meta").textContent = compactTime(snapshot.latest_signal_run_at || "n/a");

      const executionRun = snapshot.latest_execution_run;
      if (executionRun) {
        const executionStatus = executionRun.status || (Number(executionRun.rejected_orders || 0) > 0 ? "alert" : "ok");
        document.getElementById("execution-status").textContent = String(executionRun.fills_count || 0);
        document.getElementById("execution-status").className = `value ${statusClass(executionStatus)}`;
        document.getElementById("execution-meta").textContent = `${t("rejected")}: ${executionRun.rejected_orders || 0} | ${compactTime(executionRun.timestamp)}`;
      } else {
        document.getElementById("execution-status").textContent = "--";
        document.getElementById("execution-status").className = "value";
        document.getElementById("execution-meta").textContent = "--";
      }

      const riskStatus = snapshot.risk_status || {};
      const blocked = Boolean(riskStatus.blocked_new_orders);
      document.getElementById("risk-gate-status").textContent = blocked ? t("blocked_orders") : localizedStatus("ok");
      document.getElementById("risk-gate-status").className = `value ${statusClass(blocked ? "blocked" : "ok")}`;
      document.getElementById("risk-gate-meta").textContent = `${t("cooldown")}: ${riskStatus.cooldown_remaining_cycles || 0} | ${t("kill_switch")}: ${riskStatus.kill_switch_enabled ? t("enabled") : t("disabled")}`;

      const validationRun = snapshot.latest_validation_run;
      if (validationRun) {
        const gateStatus = validationRun.experiment_gate?.status || "watch";
        document.getElementById("validation-status").textContent = `${t("gate_status")}: ${localizedStatus(gateStatus)}`;
        document.getElementById("validation-status").className = `value ${statusClass(gateStatus)}`;
        document.getElementById("validation-meta").textContent = `${t("sharpe")}: ${Number(validationRun.sharpe || 0).toFixed(2)} | ${t("max_drawdown")}: ${pct(validationRun.max_drawdown_pct || 0)}`;
      } else {
        document.getElementById("validation-status").textContent = "--";
        document.getElementById("validation-status").className = "value";
        document.getElementById("validation-meta").textContent = "--";
      }

      document.getElementById("ds-status").textContent = localizedDsMode(snapshot.ds_mode || "disabled");
      document.getElementById("ds-status").className = `value ${statusClass(snapshot.ds_mode === "shadow" ? "ok" : "watch")}`;
      document.getElementById("ds-meta").textContent = snapshot.latest_ds_approval?.decision_id
        ? `${t("approval_status")}: ${localizedStatus(snapshot.latest_ds_approval.status || "unknown")} | ${compactTime(snapshot.latest_ds_approval.timestamp || "n/a")}`
        : compactTime(snapshot.latest_ds_decision_at || "n/a");
    }

    function renderPositionsTable(context, bodyId, metaId) {
      const body = document.getElementById(bodyId);
      document.getElementById(metaId).textContent = t("snapshot_meta", {
        timestamp: compactTime(context.timestamp),
        persisted: compactTime(context.last_equity_snapshot_at || "n/a"),
      });
      if (!Array.isArray(context.positions) || !context.positions.length) {
        body.innerHTML = `<tr><td class="empty" colspan="6">${escapeHtml(t("no_positions"))}</td></tr>`;
        return;
      }
      body.innerHTML = context.positions.map((position) => `
        <tr>
          <td>${escapeHtml(position.symbol)}</td>
          <td class="mono">${escapeHtml(position.quantity)}</td>
          <td>${escapeHtml(money(position.average_entry_price))}</td>
          <td>${escapeHtml(money(position.mark))}</td>
          <td class="${escapeHtml(statusClass(Number(position.unrealized_pnl) < 0 ? "alert" : "ok"))}">${escapeHtml(money(position.unrealized_pnl))}</td>
          <td>${position.stop_loss ? escapeHtml(money(position.stop_loss)) : escapeHtml(t("none"))}</td>
        </tr>
      `).join("");
    }

    function renderNavChart(context, canvasId, metaId, color) {
      const equityCurve = context.timeseries?.equity_curve || [];
      const series = equityCurve.map((row) => ({ label: row.timestamp, value: Number(row.nav) }));
      drawLineChart(document.getElementById(canvasId), series, {
        color,
        fill: true,
        height: 260,
      });
      const first = equityCurve[0];
      const last = equityCurve[equityCurve.length - 1];
      document.getElementById(metaId).textContent = equityCurve.length
        ? `${t("chart_latest", { value: money(last.nav) })} | ${t("chart_range", {
            start: compactTime(first.timestamp),
            end: compactTime(last.timestamp),
          })}`
        : t("chart_empty");
    }

    function renderPriceTrends(context, label) {
      const grid = document.getElementById("price-trends-grid");
      const positions = Array.isArray(context?.positions) ? context.positions : [];
      const historyMap = context?.timeseries?.market_prices || {};
      document.getElementById("price-trends-meta").textContent = t("held_assets", {
        label: viewLabel(label),
        count: positions.length,
      });
      if (!positions.length) {
        grid.innerHTML = `<div class="empty">${escapeHtml(t("no_positions"))}</div>`;
        return;
      }

      grid.innerHTML = positions.map((position) => {
        const history = Array.isArray(historyMap[position.symbol]) ? historyMap[position.symbol] : [];
        const last = history[history.length - 1];
        const latestText = last ? t("chart_latest", { value: money(last.price) }) : t("no_price_history");
        const rangeText = history.length
          ? t("chart_range", {
              start: compactTime(history[0].timestamp),
              end: compactTime(last.timestamp),
            })
          : t("no_price_history");
        return `
          <section class="mini-card">
            <div class="mini-card-head">
              <div class="mini-card-title">${escapeHtml(position.symbol)}</div>
              <div class="meta">${escapeHtml(latestText)}</div>
            </div>
            <canvas class="price-mini-chart" data-symbol="${escapeHtml(position.symbol)}" width="360" height="120"></canvas>
            <div class="meta">${escapeHtml(rangeText)}</div>
          </section>
        `;
      }).join("");

      positions.forEach((position) => {
        const history = Array.isArray(historyMap[position.symbol]) ? historyMap[position.symbol] : [];
        const canvas = Array.from(grid.querySelectorAll("canvas[data-symbol]"))
          .find((item) => item.dataset.symbol === position.symbol);
        if (!canvas) {
          return;
        }
        drawLineChart(
          canvas,
          history.map((row) => ({ label: row.timestamp, value: Number(row.price) })),
          {
            color: "#a12b3d",
            fill: false,
            height: 120,
          },
        );
      });
    }

    function renderSignals(signalRun, marketFetch) {
      const list = document.getElementById("signals-list");
      document.getElementById("signals-meta").textContent = t("market_signal_meta", {
        market: compactTime(marketFetch?.timestamp || "n/a"),
        signal: compactTime(signalRun?.timestamp || "n/a"),
      });
      if (!signalRun || !Array.isArray(signalRun.signals) || !signalRun.signals.length) {
        list.innerHTML = `<li class="empty">${escapeHtml(t("no_signals"))}</li>`;
        return;
      }
      const targets = Array.isArray(signalRun.targets) ? signalRun.targets : [];
      const targetText = targets.length
        ? targets.map((item) => `${item.symbol} @ ${item.target_weight}`).join(", ")
        : t("none");
      list.innerHTML = `
        <li>
          <div><span class="pill">${escapeHtml(localizedStatus(signalRun.status || "unknown"))}</span>${escapeHtml(signalRun.summary || "")}</div>
          <div class="meta">${escapeHtml(t("targets"))}: ${escapeHtml(targetText)}</div>
        </li>
      ` + signalRun.signals.slice(0, 6).map((entry) => `
        <li>
          <div>
            <strong>${escapeHtml(entry.symbol)}</strong>
            <span class="${escapeHtml(statusClass(entry.signal))}">${escapeHtml(localizedSignal(entry.signal))}</span>
          </div>
          <div class="meta">${escapeHtml(t("obs"))}=${escapeHtml(String(entry.observations))} | ${escapeHtml(t("momentum"))}=${escapeHtml(String(entry.momentum))}</div>
          <div class="meta">${escapeHtml(t("ema_slope"))}=${escapeHtml(String(entry.ema_slope))} | ${escapeHtml(t("latest"))}=${escapeHtml(money(entry.latest_price))}</div>
        </li>
      `).join("");
    }

    function renderUniverse(snapshot) {
      const universe = snapshot.universe_status || {};
      const list = document.getElementById("universe-list");
      document.getElementById("universe-meta").textContent = compactTime(universe.latest_refresh_at || "n/a");
      if (!universe.latest_refresh_at) {
        list.innerHTML = `<li class="empty">${escapeHtml(t("no_universe"))}</li>`;
        return;
      }
      list.innerHTML = `
        <li>
          <div><strong>${escapeHtml(t("last_refresh"))}</strong></div>
          <div class="meta">${escapeHtml(compactTime(universe.latest_refresh_at || "n/a"))}</div>
        </li>
        <li>
          <div><strong>${escapeHtml(t("all_count"))}</strong> ${escapeHtml(String(universe.all_count || 0))}</div>
          <div class="meta">${escapeHtml(t("filtered_count"))}: ${escapeHtml(String(universe.filtered_count || 0))}</div>
          <div class="meta">${escapeHtml(t("top120_count"))}: ${escapeHtml(String(universe.top120_count || 0))} | ${escapeHtml(t("top30_count"))}: ${escapeHtml(String(universe.top30_count || 0))}</div>
        </li>
        <li>
          <div><strong>${escapeHtml(t("ranking_rule"))}</strong></div>
          <div class="meta">${escapeHtml(String(universe.ranking_rule || ""))}</div>
        </li>
      `;
    }

    function renderNotifications(entries) {
      const list = document.getElementById("notifications-list");
      document.getElementById("notifications-meta").textContent = t("showing_limit", { count: notificationLimit });
      if (!entries.length) {
        list.innerHTML = `<li class="empty">${escapeHtml(t("no_notifications"))}</li>`;
        return;
      }
      list.innerHTML = entries.map((entry) => `
        <li>
          <div>
            <strong>${escapeHtml(entry.task || "n/a")}</strong>
            <span class="${escapeHtml(statusClass(entry.current_status || entry.status))}">${escapeHtml(localizedStatus(entry.current_status || entry.status))}</span>
          </div>
          <div>${escapeHtml(entry.did_what || "")}</div>
          <div class="meta">${escapeHtml(compactTime(entry.timestamp))} | ${escapeHtml(entry.source || "")}</div>
          <div class="meta">${escapeHtml(t("risk"))}: ${escapeHtml(entry.risk_impact || "n/a")}</div>
          <div class="meta">${escapeHtml(t("next"))}: ${escapeHtml(entry.next_step || "n/a")}</div>
        </li>
      `).join("");
    }

    function renderExperiments(items) {
      const list = document.getElementById("experiment-list");
      const rows = Array.isArray(items) ? items : [];
      document.getElementById("experiment-meta").textContent = t("showing_limit", { count: rows.length });
      if (!rows.length) {
        list.innerHTML = `<li class="empty">${escapeHtml(t("no_validation"))}</li>`;
        return;
      }
      list.innerHTML = rows.map((entry) => {
        const gateStatus = entry.experiment_gate?.status || "watch";
        return `
          <li>
            <div>
              <strong>${escapeHtml(entry.experiment_id || "n/a")}</strong>
              <span class="${escapeHtml(statusClass(gateStatus))}">${escapeHtml(localizedStatus(gateStatus))}</span>
            </div>
            <div class="meta">${escapeHtml(compactTime(entry.timestamp))} | ${escapeHtml(t("return_pct"))}: ${escapeHtml(pct(entry.return_pct || 0))}</div>
            <div class="meta">${escapeHtml(t("sharpe"))}: ${escapeHtml(Number(entry.sharpe || 0).toFixed(2))} | ${escapeHtml(t("max_drawdown"))}: ${escapeHtml(pct(entry.max_drawdown_pct || 0))}</div>
            <div class="meta">${escapeHtml(entry.summary || "")}</div>
          </li>
        `;
      }).join("");
    }

    function renderOpsTabs() {
      const items = [
        { id: "control", label: t("ops_tab_control") },
        { id: "execution", label: t("ops_tab_execution") },
        { id: "risk", label: t("ops_tab_risk") },
        { id: "validation", label: t("ops_tab_validation") },
        { id: "ds", label: t("ops_tab_ds") },
      ];
      const container = document.getElementById("ops-tabs");
      container.innerHTML = items.map((item) => `
        <button class="panel-tab ${item.id === activeOpsTab ? "is-active" : ""}" data-ops-tab="${escapeHtml(item.id)}" type="button">
          ${escapeHtml(item.label)}
        </button>
      `).join("");
      Array.from(container.querySelectorAll("button[data-ops-tab]")).forEach((button) => {
        button.addEventListener("click", () => {
          activeOpsTab = button.dataset.opsTab || "control";
          applyOpsTabVisibility();
          renderOpsTabs();
        });
      });
      applyOpsTabVisibility();
    }

    function applyOpsTabVisibility() {
      const ids = ["control", "execution", "risk", "validation", "ds"];
      ids.forEach((id) => {
        const node = document.getElementById(`ops-panel-${id}`);
        if (!node) return;
        if (id === activeOpsTab) node.classList.remove("hidden");
        else node.classList.add("hidden");
      });
    }

    function renderStrategyControl(snapshot) {
      const selection = snapshot?.strategy_selection || {};
      const list = document.getElementById("strategy-control-list");
      const enabled = Boolean(selection.enabled);
      const selected = selection.selected_strategy || "--";
      document.getElementById("strategy-control-meta").textContent = compactTime(snapshot?.timestamp || "n/a");
      list.innerHTML = `
        <li>
          <div><strong>${escapeHtml(enabled ? t("strategy_follow_enabled") : t("strategy_follow_disabled"))}</strong></div>
          <div class="meta">${escapeHtml(t("selected_strategy"))}: ${escapeHtml(String(selected))}</div>
          <div class="meta">execute-sim --decision-source strategy-selected</div>
        </li>
      `;
    }

    function renderStrategyTabs(tabs) {
      const container = document.getElementById("strategy-tabs");
      container.innerHTML = tabs.map((tab) => {
        const isOverview = tab.id === "overview";
        const secondary = isOverview
          ? `${tab.initialized_count || 0}/${tab.strategy_count || 0}`
          : (tab.initialized ? money(tab.nav || 0) : t("not_initialized"));
        const tertiary = isOverview
          ? (tab.best_strategy ? `${t("overview_best")}: ${tab.best_strategy}` : t("none"))
          : (tab.return_pct == null ? t("not_initialized") : `${t("return_pct")}: ${pct(tab.return_pct)}`);
        return `
          <button class="tab-button ${tab.id === activeView ? "is-active" : ""}" data-view="${escapeHtml(tab.id)}" type="button">
            <div class="tab-title-row">
              <span class="tab-title">${escapeHtml(isOverview ? t("overview") : tab.label)}</span>
              <span class="tab-state ${escapeHtml(statusClass(tab.status))}">${escapeHtml(localizedStatus(tab.status))}</span>
            </div>
            <div class="tab-meta">${escapeHtml(secondary)}</div>
            <div class="tab-meta">${escapeHtml(tertiary)}</div>
          </button>
        `;
      }).join("");
      Array.from(container.querySelectorAll("button[data-view]")).forEach((button) => {
        button.addEventListener("click", () => {
          setActiveView(button.dataset.view || "overview");
        });
      });
    }

    function renderStrategyCompare(snapshot) {
      const compare = snapshot.strategy_compare || {};
      const body = document.getElementById("strategy-compare-body");
      const recommendation = compare.recommended_allocation || {};
      const recommendedWeights = new Map(
        (Array.isArray(recommendation.weights) ? recommendation.weights : [])
          .filter((item) => item && item.strategy)
          .map((item) => [String(item.strategy), Number(item.weight || 0)]),
      );
      const lead = recommendation.lead_strategy ? ` | lead=${recommendation.lead_strategy}` : "";
      document.getElementById("strategy-compare-meta").textContent = `${compactTime(compare.generated_at || "n/a")}${lead}`;
      const rows = Array.isArray(compare.strategies) ? compare.strategies : [];
      if (!rows.length) {
        body.innerHTML = `<tr><td class="empty" colspan="8">${escapeHtml(t("no_strategy_compare"))}</td></tr>`;
        return;
      }
      body.innerHTML = rows.map((row) => `
        <tr>
          <td>${escapeHtml(row.strategy || "n/a")}</td>
          <td>${row.return_pct == null ? escapeHtml(t("not_initialized")) : escapeHtml(pct(row.return_pct))}</td>
          <td>${row.max_drawdown_pct == null ? escapeHtml(t("not_initialized")) : escapeHtml(pct(row.max_drawdown_pct))}</td>
          <td>${row.win_rate == null ? escapeHtml(t("not_initialized")) : escapeHtml(pct(row.win_rate))}</td>
          <td>${row.profit_factor == null ? escapeHtml(t("not_initialized")) : escapeHtml(String(row.profit_factor))}</td>
          <td>${row.turnover_ratio == null ? escapeHtml(t("not_initialized")) : escapeHtml(pct(row.turnover_ratio))}</td>
          <td>${escapeHtml(String(row.risk_trigger_count || 0))}</td>
          <td>${recommendedWeights.has(String(row.strategy || "")) ? escapeHtml(pct(recommendedWeights.get(String(row.strategy || "")))) : escapeHtml(t("not_initialized"))}</td>
        </tr>
      `).join("");
    }

    function renderOverviewStrategyCards(tabs) {
      const container = document.getElementById("overview-strategy-cards");
      const items = tabs.filter((tab) => tab.id !== "overview");
      container.innerHTML = items.map((tab) => `
        <section class="summary-card">
          <div class="tab-title-row">
            <span class="summary-card-label">${escapeHtml(tab.label)}</span>
            <span class="pill ${escapeHtml(statusClass(tab.status))}">${escapeHtml(localizedStatus(tab.status))}</span>
          </div>
          <div class="summary-card-value">${escapeHtml(tab.initialized ? money(tab.nav || 0) : t("not_initialized"))}</div>
          <div class="meta">${escapeHtml(tab.return_pct == null ? t("not_initialized") : `${t("return_pct")}: ${pct(tab.return_pct)}`)}</div>
          <div class="meta">${escapeHtml(`${t("risk_triggers")}: ${tab.risk_trigger_count || 0} | ${t("positions")}: ${tab.position_count || 0}`)}</div>
        </section>
      `).join("");
    }

    function renderOverviewView(snapshot, tabs) {
      document.getElementById("strategy-workspace-meta").textContent = compactTime(snapshot.strategy_compare?.generated_at || snapshot.timestamp);
      document.getElementById("workspace-note").textContent = snapshot.latest_execution_summary || snapshot.latest_signal_summary || "--";
      renderOverviewStrategyCards(tabs);
      renderNavChart(snapshot, "nav-chart", "nav-chart-meta", "#1d6b6f");
      renderStrategyCompare(snapshot);
      renderPositionsTable(snapshot, "positions-body", "positions-meta");
    }

    function renderStrategyKpis(detail) {
      const summary = detail.summary || {};
      const container = document.getElementById("strategy-kpis");
      container.innerHTML = [
        { label: t("nav"), value: summary.nav == null ? t("not_initialized") : money(summary.nav), meta: viewLabel(detail.strategy) },
        { label: t("return_pct"), value: summary.return_pct == null ? t("not_initialized") : pct(summary.return_pct), meta: t("updated_at") + `: ${compactTime(summary.latest_updated_at || detail.timestamp)}` },
        { label: t("current_drawdown"), value: summary.current_drawdown_pct == null ? t("not_initialized") : pct(summary.current_drawdown_pct), meta: summary.max_drawdown_pct == null ? "--" : `${t("max_drawdown")}: ${pct(summary.max_drawdown_pct)}` },
        { label: t("risk_triggers"), value: String(summary.risk_trigger_count || 0), meta: summary.turnover_ratio == null ? "--" : `${t("turnover")}: ${pct(summary.turnover_ratio)}` },
        { label: t("positions"), value: String(summary.position_count || 0), meta: summary.win_rate == null ? "--" : `${t("win_rate")}: ${pct(summary.win_rate)}` },
      ].map((item) => `
        <section class="summary-card">
          <div class="summary-card-label">${escapeHtml(item.label)}</div>
          <div class="summary-card-value">${escapeHtml(item.value)}</div>
          <div class="meta">${escapeHtml(item.meta)}</div>
        </section>
      `).join("");
    }

    function renderPositionsSummary(detail) {
      const summary = detail.positions_summary || {};
      const list = document.getElementById("strategy-positions-summary-list");
      document.getElementById("strategy-positions-summary-meta").textContent = compactTime(detail.summary?.latest_updated_at || detail.timestamp);
      list.innerHTML = `
        <li>
          <div><strong>${escapeHtml(t("gross_exposure"))}</strong></div>
          <div class="meta">${escapeHtml(pct(summary.gross_exposure_pct || 0))}</div>
        </li>
        <li>
          <div><strong>${escapeHtml(t("cash_ratio"))}</strong></div>
          <div class="meta">${escapeHtml(pct(summary.cash_ratio_pct || 0))}</div>
        </li>
        <li>
          <div><strong>${escapeHtml(t("largest_position"))}</strong></div>
          <div class="meta">${escapeHtml(summary.largest_position_symbol || t("none"))}</div>
          <div class="meta">${escapeHtml(summary.largest_position_value ? money(summary.largest_position_value) : t("none"))}</div>
        </li>
        <li>
          <div><strong>${escapeHtml(t("strategy_rule"))}</strong></div>
          <div class="meta">${escapeHtml(detail.profile?.description || "--")}</div>
        </li>
      `;
    }

    function renderStrategyTrades(detail) {
      const body = document.getElementById("strategy-trades-body");
      const trades = Array.isArray(detail.recent_trades) ? detail.recent_trades : [];
      document.getElementById("strategy-trades-meta").textContent = `${trades.length} / 8`;
      if (!trades.length) {
        body.innerHTML = `<tr><td class="empty" colspan="4">${escapeHtml(t("no_trades"))}</td></tr>`;
        return;
      }
      body.innerHTML = trades.map((trade) => `
        <tr>
          <td>${escapeHtml(trade.symbol || "")}<div class="meta">${escapeHtml(compactTime(trade.timestamp || ""))}</div></td>
          <td>${escapeHtml(localizedDecisionAction(trade.side || ""))}</td>
          <td>${escapeHtml(money(trade.notional || 0))}</td>
          <td class="${escapeHtml(statusClass(Number(trade.realized_pnl || 0) < 0 ? "alert" : "ok"))}">${escapeHtml(money(trade.realized_pnl || 0))}</td>
        </tr>
      `).join("");
    }

    function renderStrategyEvents(detail) {
      const list = document.getElementById("strategy-events-list");
      const events = Array.isArray(detail.recent_events) ? detail.recent_events : [];
      document.getElementById("strategy-events-meta").textContent = `${events.length} / 8`;
      if (!events.length) {
        list.innerHTML = `<li class="empty">${escapeHtml(t("no_events"))}</li>`;
        return;
      }
      list.innerHTML = events.map((event) => `
        <li>
          <div>
            <span class="pill ${escapeHtml(statusClass(event.status))}">${escapeHtml(localizedEventCategory(event.category))}</span>
            <strong>${escapeHtml(event.title || "")}</strong>
          </div>
          <div class="meta">${escapeHtml(compactTime(event.timestamp || ""))}</div>
          <div class="meta">${escapeHtml(event.detail || "")}</div>
        </li>
      `).join("");
    }

    function renderStrategyDetail(detail) {
      document.getElementById("strategy-workspace-meta").textContent = compactTime(detail.summary?.latest_updated_at || detail.timestamp);
      document.getElementById("workspace-note").textContent = detail.latest_signal_summary || detail.profile?.description || "--";
      document.getElementById("strategy-detail-label").textContent = viewLabel(detail.strategy);
      document.getElementById("strategy-detail-title").textContent = detail.strategy;
      document.getElementById("strategy-detail-meta").textContent = `${t("updated_at")}: ${compactTime(detail.summary?.latest_updated_at || detail.timestamp)}`;
      document.getElementById("strategy-detail-note").textContent = detail.profile?.description || "--";
      renderStrategyKpis(detail);
      renderNavChart(detail, "strategy-nav-chart", "strategy-chart-meta", "#1d6b6f");
      renderPositionsSummary(detail);
      renderPositionsTable(detail, "strategy-positions-body", "strategy-positions-meta");
      renderStrategyTrades(detail);
      renderStrategyEvents(detail);
    }

    function renderStrategyLoading(view) {
      document.getElementById("strategy-workspace-meta").textContent = t("workspace_loading");
      document.getElementById("workspace-note").textContent = viewLabel(view);
      document.getElementById("strategy-detail-label").textContent = viewLabel(view);
      document.getElementById("strategy-detail-title").textContent = view;
      document.getElementById("strategy-detail-meta").textContent = t("workspace_loading");
      document.getElementById("strategy-detail-note").textContent = "";
      document.getElementById("strategy-kpis").innerHTML = `<section class="summary-card"><div class="summary-card-label">${escapeHtml(t("loading"))}</div><div class="summary-card-value">--</div></section>`;
      document.getElementById("strategy-positions-summary-list").innerHTML = `<li class="empty">${escapeHtml(t("workspace_loading"))}</li>`;
      document.getElementById("strategy-positions-body").innerHTML = `<tr><td class="empty" colspan="6">${escapeHtml(t("workspace_loading"))}</td></tr>`;
      document.getElementById("strategy-trades-body").innerHTML = `<tr><td class="empty" colspan="4">${escapeHtml(t("workspace_loading"))}</td></tr>`;
      document.getElementById("strategy-events-list").innerHTML = `<li class="empty">${escapeHtml(t("workspace_loading"))}</li>`;
      drawLineChart(document.getElementById("strategy-nav-chart"), [], { color: "#1d6b6f", fill: true, height: 260 });
      document.getElementById("strategy-chart-meta").textContent = t("workspace_loading");
    }

    function renderStrategyNotInitialized(view) {
      document.getElementById("strategy-workspace-meta").textContent = t("strategy_not_initialized");
      document.getElementById("workspace-note").textContent = viewLabel(view);
      document.getElementById("strategy-detail-label").textContent = viewLabel(view);
      document.getElementById("strategy-detail-title").textContent = view;
      document.getElementById("strategy-detail-meta").textContent = t("strategy_not_initialized");
      document.getElementById("strategy-detail-note").textContent = t("strategy_not_initialized");
      document.getElementById("strategy-kpis").innerHTML = `<section class="summary-card"><div class="summary-card-label">${escapeHtml(t("not_initialized"))}</div><div class="summary-card-value">${escapeHtml(t("not_initialized"))}</div></section>`;
      document.getElementById("strategy-positions-summary-list").innerHTML = `<li class="empty">${escapeHtml(t("strategy_not_initialized"))}</li>`;
      document.getElementById("strategy-positions-body").innerHTML = `<tr><td class="empty" colspan="6">${escapeHtml(t("strategy_not_initialized"))}</td></tr>`;
      document.getElementById("strategy-trades-body").innerHTML = `<tr><td class="empty" colspan="4">${escapeHtml(t("strategy_not_initialized"))}</td></tr>`;
      document.getElementById("strategy-events-list").innerHTML = `<li class="empty">${escapeHtml(t("strategy_not_initialized"))}</li>`;
      drawLineChart(document.getElementById("strategy-nav-chart"), [], { color: "#1d6b6f", fill: true, height: 260 });
      document.getElementById("strategy-chart-meta").textContent = t("strategy_not_initialized");
    }

    function renderExecutionPanel(context, label) {
      const executionRun = context?.latest_execution_run;
      const list = document.getElementById("execution-list");
      if (!executionRun) {
        document.getElementById("execution-panel-meta").textContent = `${viewLabel(label)} | --`;
        list.innerHTML = `<li class="empty">${escapeHtml(t("no_execution"))}</li>`;
        return;
      }
      const executionStatus = executionRun.status || (Number(executionRun.rejected_orders || 0) > 0 ? "alert" : "ok");
      document.getElementById("execution-panel-meta").textContent = t("execution_meta", {
        label: viewLabel(label),
        timestamp: compactTime(executionRun.timestamp),
        signal: compactTime(executionRun.signal_timestamp || "n/a"),
      });
      const orders = Array.isArray(executionRun.orders) ? executionRun.orders : [];
      list.innerHTML = `
        <li>
          <div><span class="pill">${escapeHtml(localizedStatus(executionStatus))}</span>${escapeHtml(executionRun.summary || "")}</div>
          <div class="meta">${escapeHtml(t("fills"))}: ${escapeHtml(String(executionRun.fills_count || 0))} | ${escapeHtml(t("rejected"))}: ${escapeHtml(String(executionRun.rejected_orders || 0))} | ${escapeHtml(t("canceled"))}: ${escapeHtml(String(executionRun.canceled_orders || 0))}</div>
          <div class="meta">${escapeHtml(t("fees"))}: ${escapeHtml(money(executionRun.fees_total || 0))} | ${escapeHtml(t("slippage"))}: ${escapeHtml(money(executionRun.slippage_total || 0))}</div>
        </li>
      ` + orders.slice(0, 4).map((order) => `
        <li>
          <div>
            <strong>${escapeHtml(order.symbol)}</strong>
            <span class="${escapeHtml(statusClass(order.status))}">${escapeHtml(localizedStatus(order.status || "unknown"))}</span>
          </div>
          <div class="meta">${escapeHtml(String(order.side || "").toUpperCase())} | req=${escapeHtml(String(order.requested_quantity || "0"))} | filled=${escapeHtml(String(order.filled_quantity_total || "0"))}</div>
          <div class="meta">${escapeHtml(t("latest"))}=${escapeHtml(money(order.avg_fill_price || order.mark_price || 0))} | remaining=${escapeHtml(String(order.remaining_quantity || "0"))}</div>
          ${order.reason ? `<div class="meta">${escapeHtml(order.reason)}</div>` : ""}
        </li>
      `).join("");
    }

    function renderRiskPanel(context, label) {
      const riskStatus = context?.risk_status || {};
      const list = document.getElementById("risk-list");
      document.getElementById("risk-panel-meta").textContent = `${viewLabel(label)} | ${compactTime(riskStatus.timestamp || context?.timestamp || "n/a")}`;
      const blockedReasons = Array.isArray(riskStatus.blocked_reasons) ? riskStatus.blocked_reasons : [];
      const circuit = context?.last_circuit_breaker_event || riskStatus.last_circuit_breaker_event;
      list.innerHTML = `
        <li>
          <div><strong>${escapeHtml(t("blocked_orders"))}</strong> <span class="${escapeHtml(statusClass(riskStatus.blocked_new_orders ? "blocked" : "ok"))}">${escapeHtml(riskStatus.blocked_new_orders ? t("active") : t("inactive"))}</span></div>
          <div class="meta">${escapeHtml(t("daily_return"))}: ${escapeHtml(pct(riskStatus.daily_return_pct || 0))}</div>
          <div class="meta">${escapeHtml(t("circuit_breaker"))}: ${escapeHtml(pct(riskStatus.daily_loss_circuit_breaker_pct || 0))}</div>
        </li>
        <li>
          <div><strong>${escapeHtml(t("kill_switch"))}</strong> <span class="${escapeHtml(statusClass(riskStatus.kill_switch_enabled ? "blocked" : "ok"))}">${escapeHtml(riskStatus.kill_switch_enabled ? t("enabled") : t("disabled"))}</span></div>
          <div class="meta">${escapeHtml(t("cooldown"))}: ${escapeHtml(String(riskStatus.cooldown_remaining_cycles || 0))} ${escapeHtml(t("cycle"))}(s)</div>
          <div class="meta">${escapeHtml(t("consecutive_losses"))}: ${escapeHtml(String(riskStatus.consecutive_loss_count || 0))} / ${escapeHtml(String(riskStatus.consecutive_loss_limit || 0))}</div>
        </li>
      `;
      if (blockedReasons.length) {
        list.innerHTML += blockedReasons.slice(0, 3).map((reason) => `
          <li>
            <div><strong>${escapeHtml(t("risk"))}</strong></div>
            <div class="meta">${escapeHtml(reason)}</div>
          </li>
        `).join("");
      }
      if (circuit && typeof circuit === "object") {
        list.innerHTML += `
          <li>
            <div><strong>${escapeHtml(t("circuit_breaker"))}</strong></div>
            <div class="meta">${escapeHtml(compactTime(circuit.timestamp || "n/a"))}</div>
            <div class="meta">${escapeHtml(pct(circuit.daily_return_pct || 0))} / ${escapeHtml(pct(circuit.threshold_pct || 0))}</div>
          </li>
        `;
      }
    }

    function renderValidationPanel(context, label) {
      const validationRun = context?.latest_validation_run;
      const list = document.getElementById("validation-list");
      if (!validationRun) {
        document.getElementById("validation-panel-meta").textContent = `${viewLabel(label)} | --`;
        list.innerHTML = `<li class="empty">${escapeHtml(t("no_validation"))}</li>`;
        return;
      }
      document.getElementById("validation-panel-meta").textContent = t("validation_meta", {
        label: viewLabel(label),
        timestamp: compactTime(validationRun.timestamp),
      });
      list.innerHTML = `
        <li>
          <div><span class="pill">${escapeHtml(localizedStatus(validationRun.status || "unknown"))}</span>${escapeHtml(validationRun.summary || "")}</div>
          <div class="meta">${escapeHtml(t("return_pct"))}: ${escapeHtml(pct(validationRun.return_pct || 0))}</div>
          <div class="meta">${escapeHtml(t("max_drawdown"))}: ${escapeHtml(pct(validationRun.max_drawdown_pct || 0))}</div>
          <div class="meta">${escapeHtml(t("annualized_return"))}: ${escapeHtml(pct(validationRun.annualized_return || 0))} | ${escapeHtml(t("annualized_volatility"))}: ${escapeHtml(pct(validationRun.annualized_volatility || 0))}</div>
          <div class="meta">${escapeHtml(t("sharpe"))}: ${escapeHtml(Number(validationRun.sharpe || 0).toFixed(2))} | ${escapeHtml(t("sortino"))}: ${escapeHtml(Number(validationRun.sortino || 0).toFixed(2))} | ${escapeHtml(t("calmar"))}: ${escapeHtml(Number(validationRun.calmar || 0).toFixed(2))}</div>
        </li>
        <li>
          <div><strong>${escapeHtml(t("win_rate"))}</strong></div>
          <div class="meta">${escapeHtml(pct(validationRun.win_rate || 0))}</div>
          <div class="meta">${escapeHtml(t("profit_factor"))}: ${escapeHtml(String(validationRun.profit_factor || "0"))}</div>
          <div class="meta">${escapeHtml(t("longest_losing_streak"))}: ${escapeHtml(String(validationRun.longest_losing_streak || 0))}</div>
        </li>
      `;
    }

    function renderDsPanel(context, label) {
      const list = document.getElementById("ds-list");
      const rejectionList = document.getElementById("ds-rejection-list");
      document.getElementById("ds-panel-meta").textContent = `${viewLabel(label)} | ${compactTime(context?.latest_ds_decision_at || context?.timestamp || "n/a")}`;
      document.getElementById("ds-rejection-meta").textContent = compactTime(context?.latest_ds_rejection_at || "n/a");

      if (context?.profile && !context.profile.uses_ds) {
        list.innerHTML = `<li class="empty">${escapeHtml(t("no_ds_applicable"))}</li>`;
        rejectionList.innerHTML = `<li class="empty">${escapeHtml(t("no_ds_rejection"))}</li>`;
        return;
      }

      const mode = context?.ds_mode || "disabled";
      const latestDecision = context?.latest_ds_decision;
      if (!latestDecision || !latestDecision.payload) {
        list.innerHTML = `<li class="empty">${escapeHtml(t("no_ds_decision"))}</li>`;
      } else {
        const payload = latestDecision.payload;
        const decisions = Array.isArray(payload.decisions) ? payload.decisions : [];
        list.innerHTML = `
          <li>
            <div><span class="pill">${escapeHtml(localizedDsMode(mode))}</span>${escapeHtml(latestDecision.summary || "")}</div>
            <div class="meta">${escapeHtml(t("market_regime"))}: ${escapeHtml(String(payload.market_regime || "n/a"))}</div>
            <div class="meta">${escapeHtml(t("global_risk_mode"))}: ${escapeHtml(String(payload.global_risk_mode || "n/a"))}</div>
          </li>
        ` + decisions.slice(0, 4).map((decision) => `
          <li>
            <div>
              <strong>${escapeHtml(decision.symbol)}</strong>
              <span class="${escapeHtml(statusClass(decision.action === "buy" ? "ok" : (decision.action === "sell" ? "watch" : "flat")))}">${escapeHtml(localizedDecisionAction(decision.action))}</span>
            </div>
            <div class="meta">target=${escapeHtml(String(decision.target_weight || "0"))} | ${escapeHtml(t("confidence"))}=${escapeHtml(String(decision.confidence || "0"))}</div>
            <div class="meta">${escapeHtml(t("stop_loss_pct"))}=${escapeHtml(pct(decision.stop_loss_pct || 0))} | ${escapeHtml(t("take_profit_pct"))}=${escapeHtml(pct(decision.take_profit_pct || 0))}</div>
          </li>
        `).join("");
      }

      const latestRejection = context?.latest_ds_rejection;
      if (!latestRejection) {
        rejectionList.innerHTML = `<li class="empty">${escapeHtml(t("no_ds_rejection"))}</li>`;
      } else {
        rejectionList.innerHTML = `
          <li>
            <div><span class="pill">${escapeHtml(localizedStatus(latestRejection.status || "unknown"))}</span>${escapeHtml(latestRejection.reason || "")}</div>
            <div class="meta">${escapeHtml(compactTime(latestRejection.timestamp || "n/a"))} | ${escapeHtml(String(latestRejection.source || ""))}</div>
          </li>
        `;
      }
    }

    function renderHealth(healthPayload) {
      const status = healthPayload?.status || "unknown";
      document.getElementById("health-status").textContent = localizedStatus(status);
      document.getElementById("health-status").className = `value ${statusClass(status)}`;
      document.getElementById("health-meta").textContent = t("health_checks", {
        count: Array.isArray(healthPayload?.checks) ? healthPayload.checks.length : 0,
      });
    }

    function showOverviewView() {
      document.getElementById("overview-view").classList.remove("hidden");
      document.getElementById("strategy-view").classList.add("hidden");
    }

    function showStrategyView() {
      document.getElementById("overview-view").classList.add("hidden");
      document.getElementById("strategy-view").classList.remove("hidden");
    }

    function renderContextPanels(context, label) {
      if (!context) {
        document.getElementById("execution-panel-meta").textContent = `${viewLabel(label)} | ${t("workspace_loading")}`;
        document.getElementById("execution-list").innerHTML = `<li class="empty">${escapeHtml(t("workspace_loading"))}</li>`;
        document.getElementById("risk-panel-meta").textContent = `${viewLabel(label)} | ${t("workspace_loading")}`;
        document.getElementById("risk-list").innerHTML = `<li class="empty">${escapeHtml(t("workspace_loading"))}</li>`;
        document.getElementById("validation-panel-meta").textContent = `${viewLabel(label)} | ${t("workspace_loading")}`;
        document.getElementById("validation-list").innerHTML = `<li class="empty">${escapeHtml(t("workspace_loading"))}</li>`;
        document.getElementById("ds-panel-meta").textContent = `${viewLabel(label)} | ${t("workspace_loading")}`;
        document.getElementById("ds-list").innerHTML = `<li class="empty">${escapeHtml(t("workspace_loading"))}</li>`;
        document.getElementById("ds-rejection-meta").textContent = t("workspace_loading");
        document.getElementById("ds-rejection-list").innerHTML = `<li class="empty">${escapeHtml(t("workspace_loading"))}</li>`;
        return;
      }
      renderExecutionPanel(context, label);
      renderRiskPanel(context, label);
      renderValidationPanel(context, label);
      renderDsPanel(context, label);
      renderPriceTrends(context, label);
    }

    function renderStrategyWorkspace() {
      if (!lastPayload) {
        return;
      }
      const tabs = Array.isArray(lastPayload.strategy_tabs) ? lastPayload.strategy_tabs : [];
      const validViews = new Set(tabs.map((tab) => tab.id));
      if (!validViews.has(activeView)) {
        activeView = lastPayload.default_strategy_view || "overview";
        updateUrlState();
      }
      renderStrategyTabs(tabs);

      if (activeView === "overview") {
        showOverviewView();
        renderOverviewView(lastPayload.snapshot, tabs);
        renderContextPanels(lastPayload.snapshot, "overview");
        return;
      }

      showStrategyView();
      const detail = strategyCache.get(activeView);
      if (!detail) {
        renderStrategyLoading(activeView);
        renderContextPanels(null, activeView);
        return;
      }
      if (!detail.initialized) {
        renderStrategyNotInitialized(activeView);
      } else {
        renderStrategyDetail(detail);
      }
      renderContextPanels(detail, activeView);
    }

    function renderAll() {
      applyI18n();
      renderOpsTabs();
      if (!lastPayload) {
        return;
      }
      renderRootCards(lastPayload.snapshot);
      renderSignals(lastPayload.latest_signal_run, lastPayload.latest_market_fetch);
      renderUniverse(lastPayload.snapshot);
      renderNotifications(lastPayload.latest_notifications || []);
      renderExperiments(lastPayload.experiment_history || []);
      renderStrategyControl(lastPayload.snapshot);
      renderStrategyWorkspace();
      if (lastHealth) {
        renderHealth(lastHealth);
      }
    }

    async function loadStrategyDetail(view, options = {}) {
      if (view === "overview") {
        return null;
      }
      if (!options.force && strategyCache.has(view)) {
        return strategyCache.get(view);
      }
      const response = await fetch(`/api/strategy?name=${encodeURIComponent(view)}`, { cache: "no-store" });
      const payload = await response.json();
      if (!response.ok) {
        throw new Error(payload.error || `HTTP ${response.status}`);
      }
      strategyCache.set(view, payload.strategy);
      return payload.strategy;
    }

    async function setActiveView(view) {
      activeView = view || "overview";
      updateUrlState();
      renderStrategyWorkspace();
      if (activeView !== "overview") {
        try {
          await loadStrategyDetail(activeView);
          if (activeView === view) {
            renderStrategyWorkspace();
          }
        } catch (error) {
          renderRefreshError(error.message);
        }
      }
    }

    function renderRefreshError(message) {
      const text = t("refresh_failed", { message });
      document.getElementById("notifications-list").innerHTML = `<li class="empty">${escapeHtml(text)}</li>`;
      document.getElementById("signals-list").innerHTML = `<li class="empty">${escapeHtml(text)}</li>`;
      document.getElementById("universe-list").innerHTML = `<li class="empty">${escapeHtml(text)}</li>`;
      document.getElementById("execution-list").innerHTML = `<li class="empty">${escapeHtml(text)}</li>`;
      document.getElementById("risk-list").innerHTML = `<li class="empty">${escapeHtml(text)}</li>`;
      document.getElementById("validation-list").innerHTML = `<li class="empty">${escapeHtml(text)}</li>`;
      document.getElementById("ds-list").innerHTML = `<li class="empty">${escapeHtml(text)}</li>`;
      document.getElementById("ds-rejection-list").innerHTML = `<li class="empty">${escapeHtml(text)}</li>`;
      document.getElementById("price-trends-grid").innerHTML = `<div class="empty">${escapeHtml(text)}</div>`;
      document.getElementById("strategy-compare-body").innerHTML = `<tr><td colspan="8" class="empty">${escapeHtml(text)}</td></tr>`;
      document.getElementById("positions-body").innerHTML = `<tr><td colspan="6" class="empty">${escapeHtml(text)}</td></tr>`;
      document.getElementById("strategy-positions-body").innerHTML = `<tr><td colspan="6" class="empty">${escapeHtml(text)}</td></tr>`;
      document.getElementById("strategy-trades-body").innerHTML = `<tr><td colspan="4" class="empty">${escapeHtml(text)}</td></tr>`;
      document.getElementById("strategy-events-list").innerHTML = `<li class="empty">${escapeHtml(text)}</li>`;
      document.getElementById("experiment-list").innerHTML = `<li class="empty">${escapeHtml(text)}</li>`;
      document.getElementById("strategy-control-list").innerHTML = `<li class="empty">${escapeHtml(text)}</li>`;
    }

    async function refresh() {
      try {
        const requests = [
          fetch(`/api/status?n=${notificationLimit}`, { cache: "no-store" }),
          fetch("/api/health", { cache: "no-store" }),
        ];
        if (activeView !== "overview") {
          requests.push(fetch(`/api/strategy?name=${encodeURIComponent(activeView)}`, { cache: "no-store" }));
        }
        const responses = await Promise.all(requests);
        const statusPayload = await responses[0].json();
        const healthPayload = await responses[1].json();
        if (!responses[0].ok) {
          throw new Error(statusPayload.error || `HTTP ${responses[0].status}`);
        }
        if (!responses[1].ok) {
          throw new Error(healthPayload.error || `HTTP ${responses[1].status}`);
        }
        if (responses[2]) {
          const strategyPayload = await responses[2].json();
          if (!responses[2].ok) {
            throw new Error(strategyPayload.error || `HTTP ${responses[2].status}`);
          }
          strategyCache.set(activeView, strategyPayload.strategy);
        }
        lastPayload = statusPayload;
        lastHealth = healthPayload;
        renderAll();
      } catch (error) {
        renderRefreshError(error.message);
      }
    }

    document.getElementById("lang-select").addEventListener("change", (event) => {
      setLang(event.target.value);
    });

    window.addEventListener("resize", () => {
      clearTimeout(resizeTimer);
      resizeTimer = window.setTimeout(() => {
        renderStrategyWorkspace();
      }, 120);
    });

    currentLang = detectInitialLang();
    activeView = detectInitialView();
    updateUrlState();
    applyI18n();
    refresh();
    setInterval(refresh, 5000);
