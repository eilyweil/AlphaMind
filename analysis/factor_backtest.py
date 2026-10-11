"""沪深300 截面动量组合回测（12-1），月频调仓、等权、真实成本。

信号：r = P(t-21) / P(t-252) - 1，月末收盘算信号 → 次月首个交易日开盘成交。
成本：佣金万2.5(最低5元)、印花税卖出0.05%、过户费双边0.001%、滑点双边各 10bp。
约束：100 股整手、停牌跳过、一字涨停跳过（近似）、T+1（月频天然满足）。
"""
import numpy as np
import pandas as pd


def _monthly_rebalances(dates) -> list:
    """返回 [(signal_date, exec_date)]：signal=月末最后交易日，exec=次月首个交易日。"""
    dates = list(pd.DatetimeIndex(dates))
    md = {}
    for d in dates:
        md.setdefault((d.year, d.month), []).append(d)
    keys = sorted(md)
    out = []
    for i in range(len(keys) - 1):
        out.append((md[keys[i]][-1], md[keys[i + 1]][0]))
    return out


def _limit_up_price(prev_close: float, code: str) -> float:
    """涨停价（近似：创业/科创 20%，其余 10%）。"""
    pct = 0.20 if code.startswith(("300", "301", "688", "689")) else 0.10
    return round(prev_close * (1 + pct), 2)


def _buy_cost(amt, commission, min_commission, transfer):
    return max(min_commission, amt * commission) + amt * transfer


def _sell_cost(amt, commission, min_commission, stamp, transfer):
    return max(min_commission, amt * commission) + amt * stamp + amt * transfer


def _simulate(close, open_, plan, exposures, initial=1_000_000.0,
              commission=0.00025, min_commission=5.0, stamp=0.0005,
              transfer=0.00001, slippage=0.001, lot=100):
    """共享的逐日撮合循环。

    plan: {exec_d: [codes]} 每次调仓的目标持仓；exposures: {exec_d: 目标仓位 0..1}，缺省满仓。
    支持「目标仓位 < 1」即部分资金留现金（趋势风控 / 波动率目标用）。
    """
    codes = list(close.columns)
    prev_close = close.shift(1)
    dates = list(close.index)
    shares = {c: 0 for c in codes}
    cash = float(initial)
    nav = []
    total_sell = total_buy = 0.0
    first_trade_date = None

    for i, d in enumerate(dates):
        if d in plan:
            op = open_.iloc[i]
            pc = prev_close.iloc[i]
            # 当前组合开盘市值
            port_val = cash + sum(
                shares[c] * (op[c] if pd.notna(op[c]) else 0.0) for c in shares
            )
            exposure = float(exposures.get(d, 1.0))
            # 可买入标的（停牌 / 一字涨停剔除）
            buyable = []
            for c in plan[d]:
                o = op[c]
                if pd.isna(o) or o <= 0:
                    continue
                p = pc[c]
                if pd.isna(p):
                    continue
                if o >= _limit_up_price(p, c):
                    continue
                buyable.append(c)

            if buyable:
                target = (port_val * exposure) / len(buyable)
                target_shares = {}
                for c in buyable:
                    px = op[c] * (1 + slippage)
                    q = int(target / (px * lot)) * lot
                    target_shares[c] = q
                # 卖出：目标为 0 或更少
                for c, sh in list(shares.items()):
                    tgt = target_shares.get(c, 0)
                    if sh > tgt:
                        o = op[c]
                        if pd.notna(o) and o > 0:
                            amt = (sh - tgt) * o * (1 - slippage)
                            cost = _sell_cost(amt, commission, min_commission, stamp, transfer)
                            cash += amt - cost
                            total_sell += amt
                            shares[c] = tgt
                # 买入：目标更多
                for c, tgt in target_shares.items():
                    cur = shares.get(c, 0)
                    if tgt > cur:
                        o = op[c]
                        px = o * (1 + slippage)
                        buy_q = tgt - cur
                        amt = buy_q * px
                        cost = _buy_cost(amt, commission, min_commission, transfer)
                        if amt + cost <= cash:
                            cash -= amt + cost
                            total_buy += amt
                            shares[c] = tgt
                        else:  # 现金不足：能买多少整手买多少
                            affordable = int((cash - cost) / (px * lot)) * lot
                            if affordable > 0:
                                amt2 = affordable * px
                                cost2 = _buy_cost(amt2, commission, min_commission, transfer)
                                cash -= amt2 + cost2
                                total_buy += amt2
                                shares[c] = cur + affordable
            else:  # 全部买不进：清掉能卖的，转现金
                for c, sh in list(shares.items()):
                    if sh > 0:
                        o = op[c]
                        if pd.notna(o) and o > 0:
                            amt = sh * o * (1 - slippage)
                            cost = _sell_cost(amt, commission, min_commission, stamp, transfer)
                            cash += amt - cost
                            total_sell += amt
                            shares[c] = 0

        if first_trade_date is None and any(v > 0 for v in shares.values()):
            first_trade_date = d

        eq = cash + sum(
            shares[c] * (close.iloc[i][c] if pd.notna(close.iloc[i][c]) else 0.0)
            for c in shares
        )
        nav.append((d, eq))

    nav_df = pd.DataFrame(nav, columns=["date", "strategy"]).set_index("date")
    if first_trade_date is not None:
        nav_df = nav_df[nav_df.index >= first_trade_date]
    return nav_df, total_sell, total_buy


def _finish(nav_df, bench, initial, total_sell, total_buy, **extra):
    """对齐基准 + 计算指标 + 组装返回 dict（共享）。"""
    bench_s = bench.set_index("date")["close"] if "date" in bench.columns else bench["close"]
    bench_s = bench_s.reindex(nav_df.index).ffill()
    nav_df["bench"] = initial * bench_s / bench_s.iloc[0]
    metrics = _compute_metrics(nav_df, initial, total_sell)
    annual = _annual_table(nav_df)
    out = {
        "nav": nav_df.reset_index(),
        "metrics": metrics,
        "annual": annual,
        "turnover_sell": float(total_sell),
        "turnover_buy": float(total_buy),
    }
    out.update(extra)
    return out


def run_factor_backtest(close, open_, bench, constituents, names=None, top_n=30,
                        skip_recent=21, lookback=252, initial=1_000_000.0,
                        commission=0.00025, min_commission=5.0, stamp=0.0005,
                        transfer=0.00001, slippage=0.001, lot=100) -> dict:
    """经典 12-1 动量（裸动量）：月末按动量排序选前 top_n，次月首日开盘等权买入。"""
    codes = [c for c in close.columns if c in constituents]
    close = close[codes].astype(float)
    open_ = open_[codes].astype(float)
    # 12-1 动量（日历口径：向前 21 / 252 个交易日）
    mom = close.shift(skip_recent) / close.shift(lookback) - 1

    rebalances = _monthly_rebalances(close.index)

    # 预计算每次调仓选股（只依赖信号，与资金无关）
    plan = {}
    for signal, exec_d in rebalances:
        r = mom.loc[signal].dropna()
        picks = r.sort_values(ascending=False).head(top_n).index.tolist()
        if names:
            picks = [c for c in picks if "ST" not in (names.get(c) or "")]
        plan[exec_d] = picks

    nav_df, total_sell, total_buy = _simulate(
        close, open_, plan, {}, initial, commission, min_commission, stamp,
        transfer, slippage, lot,
    )
    return _finish(nav_df, bench, initial, total_sell, total_buy,
                   top_n=top_n, lookback=lookback, skip_recent=skip_recent, slippage=slippage)


def _cross_section_zscore(df: pd.DataFrame) -> pd.DataFrame:
    """逐行截面 z-score（每期在全部成分股内标准化）。"""
    mu = df.mean(axis=1)
    sd = df.std(axis=1).replace(0, np.nan)
    return df.sub(mu, axis=0).div(sd, axis=0)


def run_enhanced_backtest(close, open_, bench, constituents, names=None, top_n=30,
                          skip_recent=21, lookback=252, vol_window=60, vol_weight=0.75,
                          vol_target=0.15, trend_days=200, initial=1_000_000.0,
                          commission=0.00025, min_commission=5.0, stamp=0.0005,
                          transfer=0.00001, slippage=0.001, lot=100) -> dict:
    """多因子增强：质量动量选股 + 趋势风控 + 波动率目标。

    - 选股：composite = z(12-1 动量) + vol_weight * z(-60日波动)（动量 + 低波）
    - 趋势风控：基准收盘 < MA(trend_days) 时目标仓位 0（空仓）
    - 波动率目标：目标仓位 *= clip(vol_target / 基准60日年化波动, 0, 1)
    """
    codes = [c for c in close.columns if c in constituents]
    close = close[codes].astype(float)
    open_ = open_[codes].astype(float)

    mom = close.shift(skip_recent) / close.shift(lookback) - 1
    vol = close.ffill().pct_change(fill_method=None).rolling(vol_window).std()
    comp = _cross_section_zscore(mom) + vol_weight * _cross_section_zscore(-vol)

    bench_s = bench.set_index("date")["close"] if "date" in bench.columns else bench["close"]
    bench_s = bench_s.reindex(close.index).ffill()
    bench_ret = bench_s.pct_change(fill_method=None)

    rebalances = _monthly_rebalances(close.index)

    # 目标仓位（趋势风控 + 波动率目标）
    exposures = {}
    for signal, exec_d in rebalances:
        e = 1.0
        if trend_days:
            ma = bench_s.loc[:signal].tail(trend_days).mean()
            if bench_s.loc[signal] < ma:
                e = 0.0
        if vol_target and e > 0:
            bv = (bench_ret.rolling(vol_window).std() * np.sqrt(252)).loc[signal]
            if pd.notna(bv) and bv > 0:
                e = min(e, vol_target / bv)
        exposures[exec_d] = float(e)

    plan = {}
    for signal, exec_d in rebalances:
        r = comp.loc[signal].dropna()
        if names:
            r = r[[c for c in r.index if "ST" not in (names.get(c) or "")]]
        plan[exec_d] = r.sort_values(ascending=False).head(top_n).index.tolist()

    nav_df, total_sell, total_buy = _simulate(
        close, open_, plan, exposures, initial, commission, min_commission, stamp,
        transfer, slippage, lot,
    )
    return _finish(nav_df, bench, initial, total_sell, total_buy,
                   top_n=top_n, lookback=lookback, skip_recent=skip_recent, slippage=slippage,
                   vol_weight=vol_weight, vol_target=vol_target, trend_days=trend_days)


def _compute_metrics(nav_df: pd.DataFrame, initial: float, total_sell: float) -> dict:
    s = nav_df["strategy"]
    b = nav_df["bench"]
    sr = s.pct_change().dropna()
    n = len(s)
    years = n / 252.0

    total_s = s.iloc[-1] / s.iloc[0] - 1
    total_b = b.iloc[-1] / b.iloc[0] - 1
    ann_s = (1 + total_s) ** (1 / years) - 1 if years > 0 and total_s > -1 else 0.0
    ann_b = (1 + total_b) ** (1 / years) - 1 if years > 0 and total_b > -1 else 0.0
    vol = float(sr.std() * np.sqrt(252)) if len(sr) else 0.0
    sharpe = float(sr.mean() / sr.std() * np.sqrt(252)) if len(sr) and sr.std() > 0 else 0.0

    dd = s / s.cummax() - 1
    ddb = b / b.cummax() - 1
    max_dd = float(dd.min())
    max_dd_b = float(ddb.min())
    calmar = ann_s / abs(max_dd) if max_dd < 0 else 0.0

    # 月胜率：策略月收益 > 基准月收益 的比例
    sm = s.groupby([s.index.year, s.index.month]).last().pct_change().dropna()
    bm = b.groupby([b.index.year, b.index.month]).last().pct_change().dropna()
    common = sm.index.intersection(bm.index)
    win = float((sm.loc[common] > bm.loc[common]).mean()) if len(common) else 0.0

    # 随机基准：基准月度正收益占比（≈55–60%），用于对照「月胜率」是否真有信息量
    bench_win = float((bm > 0).mean()) if len(bm) else 0.0
    # 收益集中度：前 5 个月收益占全部月收益之和的比（>1 表示收益高度集中于少数月份）
    if len(sm) and sm.sum() > 0:
        concentration = float(sm.sort_values(ascending=False).head(5).sum() / sm.sum())
    else:
        concentration = 0.0

    avg_eq = float(s.mean())
    turn_oneway = total_sell / avg_eq / years if avg_eq > 0 and years > 0 else 0.0

    return {
        "总收益率": float(total_s),
        "基准总收益率": float(total_b),
        "年化收益率": float(ann_s),
        "基准年化": float(ann_b),
        "年化超额": float(ann_s - ann_b),
        "年化波动": vol,
        "夏普比率": sharpe,
        "最大回撤": max_dd,
        "基准最大回撤": max_dd_b,
        "Calmar": float(calmar),
        "月胜率": win,
        "基准月胜率": bench_win,
        "月收益集中度": concentration,
        "单边年换手": float(turn_oneway),
        "回测天数": n,
        "期末资金": float(s.iloc[-1]),
    }


def _annual_table(nav_df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for yr, g in nav_df.groupby(nav_df.index.year):
        if len(g) < 2:
            continue
        rs = g["strategy"].iloc[-1] / g["strategy"].iloc[0] - 1
        rb = g["bench"].iloc[-1] / g["bench"].iloc[0] - 1
        rows.append({"年份": int(yr), "策略": rs, "基准": rb, "超额": rs - rb})
    return pd.DataFrame(rows)


def pass_fail(metrics: dict) -> list:
    """通过/不通过门（返回 [(描述, 是否通过), ...]）。"""
    m = metrics
    return [
        ("年化超额 > 3%", m.get("年化超额", -9) > 0.03),
        ("年化波动 < 30%", m.get("年化波动", 9) < 0.30),
        ("夏普 > 0.5", m.get("夏普比率", -9) > 0.5),
        ("最大回撤 < 基准回撤", m.get("最大回撤", -9) > m.get("基准最大回撤", -1)),
        ("Calmar > 0.5", m.get("Calmar", -9) > 0.5),
        ("月胜率 > 55%", m.get("月胜率", -9) > 0.55),
        ("单边年换手 < 12 倍", m.get("单边年换手", 99) < 12.0),
    ]


def _fmt_pct(v):
    return f"{v * 100:.2f}%" if v is not None else "-"


def pass_fail_detail(metrics: dict) -> list:
    """门检明细（含实际值 vs 阈值），返回 [(描述, 是否通过, 实际值文本, 阈值文本), ...]。

    用于 UI 完整展示每条判定条件的实际结果，尤其「最大回撤 < 基准回撤」需先算出基准自身回撤。
    """
    m = metrics
    ex = m.get("年化超额")
    vol = m.get("年化波动")
    sp = m.get("夏普比率")
    dd = m.get("最大回撤")
    ddb = m.get("基准最大回撤")
    cal = m.get("Calmar")
    win = m.get("月胜率")
    to = m.get("单边年换手")
    return [
        ("年化超额 > 3%", (ex if ex is not None else -9) > 0.03, _fmt_pct(ex), "3%"),
        ("年化波动 < 30%", (vol if vol is not None else 9) < 0.30, _fmt_pct(vol), "30%"),
        ("夏普 > 0.5", (sp if sp is not None else -9) > 0.5, f"{sp:.2f}" if sp is not None else "-", "0.5"),
        ("最大回撤 < 基准回撤", (dd if dd is not None else -9) > (ddb if ddb is not None else -1),
         _fmt_pct(dd), _fmt_pct(ddb)),
        ("Calmar > 0.5", (cal if cal is not None else -9) > 0.5, f"{cal:.2f}" if cal is not None else "-", "0.5"),
        ("月胜率 > 55%", (win if win is not None else -9) > 0.55, _fmt_pct(win), "55%"),
        ("单边年换手 < 12 倍", (to if to is not None else 99) < 12.0, f"{to:.1f} 倍" if to is not None else "-", "12 倍"),
    ]


def walkforward_rubric(rounds: pd.DataFrame) -> dict:
    """根据 walk-forward 各轮结果给出稳健性判读（对应评审要点 4–8）。

    rounds: DataFrame，列含 轮次 / 年化超额 / 夏普 / Calmar / 月胜率。
    返回 {'observations': [(标记, 描述), ...], 'rating': 6.5|4.0, 'verdict': str}。
    """
    obs = []
    rating = 6.5

    def _val(r, k):
        v = r.get(k)
        return v if pd.notna(v) else None

    def _excess(i):
        for _, r in rounds.iterrows():
            if r["轮次"] == i:
                return _val(r, "年化超额")
        return None

    def _r(v):
        return f"{v * 100:.1f}%" if v is not None else "缺失"

    # 4 / 5. 全期夏普稳健区间（用各轮夏普均值近似全期水平）
    sharps = [_val(r, "夏普") for _, r in rounds.iterrows() if _val(r, "夏普") is not None]
    if sharps:
        avg_sharpe = float(np.mean(sharps))
        if 0.75 <= avg_sharpe <= 0.95:
            obs.append(("✅ 稳健", f"各轮夏普均值 {avg_sharpe:.2f} 落在 0.75–0.95 稳健区间，策略成立"))
        elif avg_sharpe < 0.6 or avg_sharpe > 1.2:
            obs.append(("⚠️ 参数拟合", f"各轮夏普均值 {avg_sharpe:.2f} 脱离稳健区间（<0.6 或 >1.2），疑似参数拟合，评级由 6.5 下调至 4"))
            rating = 4.0
        else:
            obs.append(("🟡 边缘", f"各轮夏普均值 {avg_sharpe:.2f} 处于 0.6–1.2 非极端区间，需结合各轮表现综合判断"))

    # 6. 第 2、3 轮年化超额 ≥ 3%
    r2, r3 = _excess(2), _excess(3)
    if r2 is not None and r3 is not None and r2 >= 0.03 and r3 >= 0.03:
        obs.append(("✅ 及格线守住", f"第 2、3 轮年化超额 {_r(r2)} / {_r(r3)} 均 ≥3%"))
    else:
        obs.append(("⚠️ 及格线失守", f"第 2、3 轮年化超额未同时 ≥3%（{_r(r2)} / {_r(r3)}）"))

    # 7. 第 4 轮超额跌至 3% 以下 → 超额高度绑定动量窗口
    r4 = _excess(4)
    if r4 is not None and r4 < 0.03:
        obs.append(("🔴 超额绑定窗口", f"第 4 轮年化超额 {_r(r4)} 跌至 3% 以下——超额高度绑定所选动量窗口，比第 2、3 轮失败更严重"))

    # 8. 任一轮 Calmar 与月胜率同时跌破 0.5 与 55%
    bad = []
    for _, r in rounds.iterrows():
        cal, win = _val(r, "Calmar"), _val(r, "月胜率")
        if cal is not None and win is not None and cal < 0.5 and win < 0.55:
            bad.append(int(r["轮次"]))
    if bad:
        obs.append(("🔴 单一参数", f"第 {','.join(map(str, bad))} 轮 Calmar 与月胜率同时跌破 0.5 与 55%——该策略仅在单一参数下可用"))

    verdict = "稳健（评级 6.5）" if rating >= 6.5 else "参数拟合（评级 4.0）"
    return {"observations": obs, "rating": rating, "verdict": verdict}
