# The Shadow Price of Latency: Improving Intraday Fill Ratios in Foreign Exchange Markets

Alvaro Cartea ´ a,b, Leandro S´anchez-Betancourta,c

<sup>a</sup>Mathematical Institute, University of Oxford, Oxford, UK <sup>b</sup>Oxford-Man Institute of Quantitative Finance, Oxford, UK <sup>c</sup>LMAX Exchange, London, UK

#### Abstract

Latency is the time delay between an exchange streaming market data to a trader, the trader processing information and deciding to trade, and the exchange receiving the order from the trader. Liquidity takers face a moving target problem as a consequence of their latency in the marketplace. They send market orders with a limit price that aim at a price and quantity they observed in the limit order book (LOB), and by the time their order is processed by the exchange, prices could have worsened, so the order may not be filled, or prices could have improved, so the order is filled at a better price. In this paper we provide a model to compute the price that liquidity takers would be willing to pay to reduce their latency in the marketplace. To this end, we derive a latency-optimal strategy that specifies the limit price of liquidity taking orders to increase the chances of filling orders if, due to latency, prices or quantities in the LOB have worsened. The latency-optimal strategy balances the tradeoff between the costs of walking the LOB and targeting a desired percentage of filled orders over a period of time. We employ the cost of improving fills with the latency-optimal strategy to compute the shadow price of latency. Finally, we use a proprietary data set of foreign exchange (FX) to compute the maximum price that a FX trader would be willing to pay for co-location and hardware to reduce their latency in the marketplace.

Keywords: Latency, fill ratio, high-frequency trading, algorithmic trading.

# 1. Introduction

With the advent of computerized trading, the speed at which agents operate in electronic markets is down to milliseconds or microseconds. Speed to process information and make

Email addresses: alvaro.cartea@maths.ox.ac.uk (Alvaro Cartea), ´ leandro.sanchezbetancourt@maths.ox.ac.uk (Leandro S´anchez-Betancourt)

Preprint submitted to TBA November 23, 2018

<sup>✩</sup>We are grateful to Ben Hambly, Sam Howison, Lane Hughston, Jos´e Penalva, and Andrew Stewart for useful discussions. We are also grateful to seminar participants at LMAX Exchange, King's College London, University of Oxford, Cass Business School, University of Toronto, 10th World Congress of The Bachelier Finance Society (Dublin 2018), Ecole Polytechnique, Lancaster University, Universit´e Paris 1 Panth´eon- ´ Sorbonne, INFORMS (Phoenix 2018), and Princeton University for their comments and suggestions.

decisions is essential to the success of trading strategies and being faster than one's peers provides a valuable competitive edge. Traders require time to execute strategies and their instructions take time to arrive and to be processed by the exchange. This time delay, known as latency, affects the efficacy of trading strategies because, in the meantime, the exchange processes other instructions that update the limit order book (LOB) with information not known by the trader at the time she executed the strategy.

In foreign exchange (FX) markets, the supply of spot currency pairs displayed in the LOB might undergo thousands of updates over very short periods of time, see [Gould et al.](#page-27-0) [\(2016\)](#page-27-0). When the best bid and best ask prices in the LOB are changing very rapidly, liquidity takers face a moving target problem as a consequence of their latency in the marketplace. Liquidity takers send market orders with a limit price (MOLP) that aim at a price and quantity they have observed in the LOB, but by the time their order is processed by the exchange, prices or quantities may have worsened, so the order cannot be filled; alternatively, prices or quantities may have improved, so the order is filled at better prices.

In this paper, we show how to compute the price that a liquidity taker is willing to pay to reduce their latency in the marketplace. We summarize the steps we take. One, we develop a latency-optimal strategy to improve the chances that liquidity taking orders are filled. Two, we compute the costs borne by the strategy. These costs consist of the slippage received to ensure that the order is filled, which is negative if prices or quantities worsen, or is positive if prices or quantities improve. Three, we build a function that links latency, fill ratios, and costs borne by the latency-optimal strategy. With this function, we compute the shadow price of latency that a trader would be willing to pay for co-location and hardware to reduce their latency in the marketplace.

Specifically, in our approach we show how the FX trader chooses the price limit of the MOLP in an optimal way to improve fill ratios over a period of time (days, weeks, months), while keeping orders exposed to receiving a price improvement. Traders can buffer the adverse effects of missing a trade by specifying a price limit in their market orders to increase the probability of filling the order when it is processed by the exchange. This price limit consists of the best price seen by the trader in the LOB, plus a discretionary buffer that determines the number of ticks the order can walk the LOB. This buffer does not preclude the order from being filled at better prices if the LOB is updated with more favourable prices or quantities.

Increasing fill ratios is costly. Everything else being equal, the chances of filling a MOLP increase if the order can walk the LOB. Thus, there is a tradeoff between ensuring high fill ratios and the execution costs borne by the trading strategy. In our model, the problem solved by the trader balances this tradeoff by optimizing the price limit specified in the MOLP, while targeting a fill ratio over a trading horizon. The trader's optimal strategy specifies the discretion for each transaction depending on the proportion of orders that have been filled, how far the strategy is from the target fill ratio, the cost of walking the LOB, and the volatility of the exchange rate.

We employ a proprietary data set of FX trades to analyze the performance of the optimal strategy developed here. The data are provided by LMAX Exchange – an electronic multilateral trading facility in the FX market (www.lmax.com). We use transaction data for two FX traders, trader 1 (T1) and trader 2 (T2), to compare the fill ratios they have achieved to those attainable with the optimal strategy derived in this paper. The data spans a set of dates from December 2016 to March 2017. During this period both traders filled between approximately 80% and 90% of their liquidity taking orders in the currency pair US dollar and Japanese yen, which we refer to as the USD/JPY pair. Latency causes T1 and T2 to miss trades because by the time the exchange processes their orders, the best bid and best ask prices in the LOB are updated. The effect of latency on trade fills is exacerbated during times of heightened volatility in the exchange rate. When volatility is arranged in quartiles, we find that 36.5% (resp. 40.0%) of T1's (resp. T2's) unfilled trades occur in the top quartile of volatility.

Clearly, due to latency, trades are not filled because the market moves away from the prices and quantities that T1 and T2 are attempting to achieve. If T1 and T2 were to return to the market to complete unfilled trades, the prices they would receive are highly likely worse than those at which they attempted in the original trade. We compare the costs of the latency-optimal strategy to the mark-to-market costs of orders that walk the LOB until filled. We assume these orders are sent 20ms or 100ms after the exchange receives the instruction to execute the orders that could not be filled. We find that the average mark-to-market cost for T1's missed trades is 2.33 and 2.88 ticks and for T2 is 3.18 and 3.06 ticks, 20ms and 100ms later respectively (in the currency pair USD/JPY one tick is 10<sup>−</sup><sup>3</sup> JPY).[1,](#page-2-0)[2](#page-2-1)

We employ the optimal strategy developed here to show the tradeoff between increasing fill ratios and the costs incurred by the strategy. For example, for a particular choice of model parameters, we show that T1 and T2 can increase the percentage of filled trades, during the period 5 December 2016 to 31 March 2017, to 99% for both traders. The increase in the fill ratios is due to the discretion included in the liquidity taking orders to walk the book, which come at a cost. In this example, the average cost incurred by T1 to fill missed trades is 1.76 ticks and for T2 is 1.24 ticks. On the other hand, the mark-to-market average cost of filling the missed trades (which were filled by the optimal strategy) with market orders 20ms and 100ms later is 2.01 and 2.58 ticks respectively for T1, and 2.82 and 2.75 ticks respectively for T2.

The performance of the optimal strategy is more remarkable during times of heightened volatility of the exchange rate. In the top quartile of volatility, the average cost of filling missed trades is 1.88 ticks when T1 employs the optimal strategy, while the mark-to-market average cost of filling these missed trades with market orders 100ms later is 3.04 ticks. Similarly, for T2 the average cost of filling missed trades with the optimal strategy is 1.86 ticks, while the mark-to-market average cost of filling the missed trades with a market order 100ms later is 3.31 ticks.

Finally, we use the proprietary data to map various levels of latency to the corresponding

<span id="page-2-0"></span><sup>1</sup>The average mark-to-market cost is calculated by taking the difference between the cost of filling all the volume missed in the order and the cost that the trader initially attempted to pay to fill the order, and dividing by the missed volume of the order. This quantity is multiplied by 10<sup>3</sup> to express it in ticks.

<span id="page-2-1"></span><sup>2</sup>From February 2018, the tick size for the pair USD/JPY is 10<sup>−</sup><sup>4</sup> JPY in LMAX Exchange Tokyo.

percentage of filled orders. We use this mapping to calculate the shadow price of latency that T1 would be willing to pay to reduce latency in the marketplace. We show that T1 would be better off employing the latency-optimal strategy developed here, instead of investing in hardware and co-location services to reduce latency. The latency-optimal strategy is superior because it not only achieves the same fill ratios as those obtained with better hardware and co-location, but it scoops price improvements that stem from orders arriving with latency at the exchange. Note that if latency is reduced with hardware and co-location, T1's liquidity taking strategy would be less affected by the moving target problem, so fill ratios are high, but would benefit little from changes in the LOB that, due to latency, provide price improvements.

A number of authors have recently addressed various aspects of latency in electronic markets. [Moallemi and Saˆglam](#page-28-0) [\(2013\)](#page-28-0) look at the cost of latency in high-frequency trading. The authors employ market data to quantify the costs of latency in equity markets and show that the latency costs are of the same order of magnitude as other trading costs such as commissions and exchange fees. The data employed are publicly available from the NYSE, which does not contain trader identification to analyze latency for individual market participants. Our study, on the other hand, focuses on liquidity taking orders in the FX market. We develop trading strategies that minimize the adverse effects of latency and use these strategies to compute the latency of liquidity takers.

The work of [Stoikov and Waeber](#page-28-1) [\(2016\)](#page-28-1) shows how to execute a large order in electronic markets by employing the volume imbalance of the LOB to predict price changes and study the effect of latency in the efficacy of the execution strategy. The authors backtest their strategy on publicly available data for US Treasury bonds and show that the advantage of observing the LOB to compute volume imbalance dissipates quickly as latency increases. [Lehalle and Mounjid](#page-28-2) [\(2017\)](#page-28-2) employ data from Nasdaq-Omx and also find that as latency increases, the informational content in the volumes of the LOB diminishes.

Recent literature on high-frequency trading and algorithmic trading discusses various characteristics of trading and how the speed of traders is used to obtain informational advantages. Other strands of the literature discuss the relationship of market quality and the speed of market participants. See for example [Bayraktar and Ludkovski](#page-27-1) [\(2010\)](#page-27-1) and [Gu´eant](#page-28-3) [\(2016\)](#page-28-3) for trading in illiquid markets. [Barger and Lorig](#page-27-2) [\(2018\)](#page-27-2) model the rapid updates of the best quotes in the LOB to propose a model of stochastic price impact.

Our paper is the first to employ proprietary data to analyze the effect of latency on the fill rates of liquidity taking strategies in FX markets and to compute the shadow price of latency for particular traders. Latency is specific to each market participant, and the effects of latency depend on the type of strategy employed by each trader. Access to proprietary data of FX transactions allows us to quantify the effects of latency on the efficacy of trading strategies and to develop and test latency-optimal strategies to compute the shadow price of latency for types of market participants.

The remainder of the paper is organized as follows. In Section [2](#page-4-0) we define latency and propose various ways to measure the fill ratios of market orders with limit price (MOsLP). In Section [3](#page-6-0) we describe the proprietary data set that we employ and we present empirical evidence of the relationship between fill ratios and the volatility of the exchange rate. In Section 4 we present the model of fill ratios and solve the trader's dynamic optimization problem, where we also assume that the trader makes her model of fill ratios robust to misspecification. In Section 5 we show how we estimate model parameters, and in Section 6 we show the performance of the trading strategy. Section 7 discusses the tradeoff between latency and fill ratios and computes the shadow price of latency for T1. Finally, Section 8 concludes, and we collect proofs and results of robustness tests in the Appendix.

# <span id="page-4-0"></span>2. Latency and Fill Ratios

### 2.1. Latency

Latency is defined as the time "delay between sending a message to the market and it being received and processed by the exchange. Sometimes the time it takes for the exchange to acknowledge receipt is also accounted for", see Cartea et al. (2015). This concept is useful if traders are only interested in measuring how long it takes a message to reach the exchange once it has been sent. However, this definition is 'narrow' because it only takes into account hardware capacity and co-location to measure latency and does not account for other factors that affect how quickly the trader can process and react to market information before sending an instruction to the exchange.

In this paper we employ a broader definition of latency. To the time delay considered in the narrow definition of latency we add the time it takes the trader to execute the trading strategy. Thus, latency consists of three layers of time delay associated to these events: (i) The exchange streams quotes to the trader. (ii) The trader receives quotes from the exchange and processes this and other relevant information to make a decision. (iii) Once a decision is made, the trader sends a message to the exchange. The decision could be to trade using limit orders or MOsLP, or to amend or cancel a limit order already resting in the LOB, see Moallemi and Saĝlam (2013) and Stoikov and Waeber (2016) who employ a similar definition of latency.

MOsLP consist of two types of orders: Immediate-or-Cancel (IoC) or Fill-or-Kill (FoK). IoC and FoK are orders in which the trader specifies the maximum (minimum) price they are willing to pay (receive) when buying (selling) currency pairs. IoC is an order to buy or sell currency pairs which must be executed immediately, obeying the price limit, and any portion of the volume of the order that cannot be filled at the desired price limit is cancelled. FoK is an order to buy or sell currency pairs which must be executed immediately in full or cancelled.

We provide an example of the steps in the life of a FoK order to illustrate the effect of latency on the fill of the trade.

Assume the exchange streams a quote to a trader at time  $t_0$ . The trader receives the quote at time  $t_1 > t_0$  and at time  $t_2 > t_1$  the trader sends a buy FoK order for 100 lots of the currency pair USD/JPY. The limit price of the FoK order is the best ask streamed by the exchange at time  $t_0$ . Finally, the exchange receives and processes the order at time  $t_3 > t_2$ , thus our measure of latency is  $t_3 - t_0$ . The order will be filled in full if at time  $t_3$  the best ask in the book is equal to or lower than (i.e., price improvement) the best ask at time  $t_0$  and

there are at least 100 lots posted at that price, otherwise the order is not filled. In either case, the exchange sends a message to the trader notifying the outcome of the trade.

The effect of latency on the outcome of strategies depends on a number of factors that affect the supply and demand of liquidity in the FX market, including: magnitude of latency, type of order sent by trader, volatility of the mid-exchange rate, and trend in the mid-exchange rate.

On the supply side of liquidity, the number of updates in the LOB will determine if the trade will be filled at the price, or a better price, than that specified in the FoK order, or if the order is not filled because prices have worsened. Changes in the best quotes of the LOB are difficult to predict and depend on many factors such as news announcements and other idiosyncratic needs of the liquidity providers who send, update, and amend their limit orders in the LOB.

On the demand side of liquidity, the effect of latency will depend on the type of strategy employed by the trader. For example, for momentum trading strategies, i.e., buy before rates increase or sell before rates decrease, latency will increase the chances of missing trades and decrease the chances of obtaining price improvements.

### 2.2. Fill ratios and post-trade analysis

Fill ratios of orders sent by a trader to an exchange can be computed in a number of ways. A trader who only sends FoK orders will receive fills of all volume or nothing, as opposed to IoC orders, which can be partially filled.

A measure of fill ratio is important because it summarizes how effective an agent's strategy is in completing trades. A simple measure is to compute the number of filled orders divided by the number of trade attempts. Here we propose new measures of fill ratios that include relevant post-trade information such as orders that were filled at better prices (i.e., price improvement), and orders that were not filled, but could have been filled at worse prices, had the order walked the LOB until filled in full. Below we provide more details about the post-trade information we include in the measures of fill ratio. Next, we describe the variables and notation we employ.

We denote by n the number of MOsLP employed to compute the trader's fill ratio. Let  $\tau_1, \tau_2, \ldots, \tau_n$  be the times at which the trader sends liquidity taking orders to the exchange and denote by  $\ell_1, \ell_2, \ldots, \ell_n$  the times at which the orders are processed by the exchange,  $\ell_i > \tau_i$ .

MOsLP specify a limit price, denoted by  $L_i$ , which is the maximum (minimum) the trader is willing to pay (receive) per unit of bought (sold) currency pair. When the exchange processes the trader's message, the order is filled if there is enough liquidity resting in the LOB up to, and including, the limit price  $L_i$ . A MOLP buy (sell) with limit price  $L_i = \infty$  ( $L_i = 0$ ) will walk all levels of the LOB until the order is filled in full at the average price  $B_i$  per unit of currency pair.

The quantity  $L_i - B_i$  (which can be computed only after the exchange receives and processes the order) is important because it gives post-trade information about different outcomes such as: (i) by how much did prices move to cause the liquidity taking order to miss its target, which we refer to as *potential slippage*, or (ii) by how much did the execution

price improve, which we refer to as *price improvement*. For example, when the trader sends a buy order with a price limit of  $L_i$  per unit of currency pair, there is a price improvement if  $L_i - B_i > 0$ . On the other hand, if the average price required to fill the order is higher than limit price the trader is willing to pay, then the potential slippage is  $L_i - B_i < 0$  – note that in this second case the trader does not incur the potential slippage because the order is not filled in full due to the limit price.

Moreover, the variable  $I_i \in \{-1, 1\}$  is used to indicate the direction of the liquidity taking order, where 1 denotes a buy order and -1 denotes a sell order. Finally,  $V_i$  denotes the volume of currency pair lots the trader attempts to fill, and  $V_i^f$  denotes the filled volume, clearly  $V_i^f \leq V_i$ .

We propose three ways to compute a fill measure of n consecutive trades. These measures are based on: (1) number of trades, (2) average volume of trades, and (3) volume of trades.

1.

<span id="page-6-1"></span>
$$F_n = \frac{1}{n} \sum_{i=1}^n \mathbf{1}_{\{I_i L_i \ge I_i B_i\}} + F(n),$$
 (1)

2.

<span id="page-6-2"></span>
$$F_n^{AV} = \frac{1}{n} \sum_{i=1}^n \frac{V_i^f}{V_i} + F(n), \qquad (2)$$

3.

<span id="page-6-3"></span>
$$F_n^V = \frac{\sum_{i=1}^n V_i^f}{\sum_{i=1}^n V_i} + F(n), \qquad (3)$$

where  $\mathbf{1}$  is the indicator function and

<span id="page-6-4"></span>
$$F(n) = \zeta \frac{1}{n} \sum_{i=1}^{n} I_i \left( L_i - B_i \right)$$
(4)

is a post-trade measure of price improvement and potential slippage. Here,  $\zeta$  is a non-negative parameter to weight potential slippage and price improvement in the measure of fill ratios. Note that  $F(n) \in \mathbb{R}$ .

# <span id="page-6-0"></span>3. Empirical Analysis

#### 3.1. Data

We employ a set of proprietary data of transactions for T1 and T2 during the period 2 December 2016 to 31 March 2017 in the currency pair USD/JPY. Both traders are liquidity takers, i.e., they do not send limit orders to provide liquidity in the LOB, during the period we study. We have the following information: side of order (buy or sell), time-stamp of when the exchange processed the order, volume, currency pair, type of order (FoK, IoC), limit price  $L_i$ , and whether the order was filled and at what price(s). Finally, we have the LOB for the pair USD/JPY at millisecond intervals. A summary of the main variables is given in Table 1.

|          | Number of attempts $N$ | Successful<br>filled trades<br>(incl. partial) | Successful<br>filled trades<br>(only full) | Avg. vol. attempted $\times 10^5$ USD | Avg. filled vol. $\times 10^5$ USD | Order<br>type | $\textbf{\emph{F}}_N$ | $\bm{F}_N^{AV}$ | $\textbf{\emph{F}}_{N}^{V}$ |
|----------|------------------------|------------------------------------------------|--------------------------------------------|---------------------------------------|------------------------------------|---------------|-----------------------|-----------------|-----------------------------|
| T1<br>T2 | 116, 912<br>68, 129    | $106,878 \\ 61,440$                            | 106,878 $59,303$                           | 4.5<br>1.2                            | 4.1<br>1.0                         | FoK<br>IoC    | 90.78%<br>87.04%      | 90.78% $88.62%$ | 90.54% $79.00%$             |

<span id="page-7-0"></span>Table 1: Proprietary data and measures of fill ratios for period 2 December 2016 to 31 March 2017.

During this period, both traders send orders that aim at the best bid or best ask price that was streamed to them by the exchange. T1 sent FoK orders with zero discretion and T2 sent IoC orders with zero discretion. For a buy MOLP we define 'discretion' as the difference between the price limit and the best offer seen by the trader when she devised the strategy. Similarly, for a sell MOLP we define discretion as the difference between the best bid and the price limit of the MOLP.

### <span id="page-7-2"></span>3.2. Fill ratios and volatility

The liquidity provided in the LOB is constantly being updated as a result of news, changes in the willingness to trade of liquidity providers, and the arrival of liquidity taking orders, see for example Almgren (2012) for a discussion of trading with stochastic liquidity. Most of the updates of limit orders (cancellations, amendments, and arrival of new limit orders) take place in the best quotes and ticks closest to the prevailing mid-exchange rate. Traders with non-zero latency face a moving target problem when they attempt to hit bids and lift offers in the LOB. This problem is exacerbated during periods of high volatility of the exchange rate.

The top figure in the left-hand panel of Figure 1 shows the evolution of the fill ratio of T1's trade attempts, using measure (1) with n = 50, during 26 January 2017. The first observation in the figure is computed when the trader has attempted the 50th trade and the fill ratio is updated every time there is a new attempt.

The bottom figure in the left-hand panel shows the volatility of the mid-exchange rate over the same period. Throughout this paper volatility is computed as the standard deviation of the log-returns of the micro-exchange rate (sampled every 500 milliseconds) over a 10-minute rolling window. The micro-exchange rate at time t is denoted by  $m_t$  and given by

<span id="page-7-1"></span>
$$m_t = \frac{P_t^a Q_t^b + P_t^b Q_t^a}{Q_t^a + Q_t^b} \,, \tag{5}$$

where  $Q_t^a$  and  $Q_t^b$  are the quantities available at the best ask price (denoted by  $P_t^a$ ) and the best bid price (denoted by  $P_t^b$ ), respectively.

From Figure 1, left-hand panel, we observe the negative correlation between volatility and the fill ratios achieved by T1's strategy, which always aims at the best bid or best offer price she observed before sending the MOLP. Clearly, volatility is high when the micro-exchange rate undergoes many changes and updates – this explains why the number of unfilled MOsLP (with zero discretion to walk the book) is higher when volatility is high.

The right-hand panel of Figure 1 shows a scatter plot of fill ratio and volatility. The solid line in the figure is obtained by performing an Ordinary Least Squares (OLS) regression of fill ratio on volatility.

![](_page_8_Figure_1.jpeg)

Figure 1: Left-hand top panel: fill ratio using measure (1) with n = 50. Left-hand bottom panel: volatility of micro-exchange rate. Right-hand panel: Scatter plot and OLS regression of volatility and fill ratio. Data are from 26 January 2017.

# <span id="page-8-0"></span>4. Model

In this section we describe the model of fill ratios and the dynamic optimization problem solved by the trader. We develop the model of fills in three steps. First, we present a model for the dynamics of volatility of the micro-exchange rate. Second, we propose a model of fill ratios that includes the effect of volatility of the micro-exchange rate on fills. Third, we specify how MOsLP with discretion to walk the LOB affect the dynamics of fill ratios.

# Volatility of micro-exchange rate

We denote the volatility of the micro-exchange rate, see (5), by  $v = (v_t)_{\{0 \le t \le T\}}$  and assume it satisfies the stochastic differential equation (SDE)

<span id="page-8-2"></span><span id="page-8-1"></span>
$$dv_t = \kappa \left(\bar{v} - v_t\right) dt + \sigma_v v_t dW_t^v, \tag{6}$$

where  $\kappa > 0$  is the exponential speed at which volatility reverts to its long-term level, denoted by  $\bar{v} > 0$ ,  $\sigma_v > 0$  is a dispersion parameter (i.e., volatility of volatility), and  $W^v = (W_t^v)_{\{0 \le t \le T\}}$  is a standard Brownian motion.

In our analysis we consider other models for volatility of the micro-exchange rate. In Appendix A.4 we show results when volatility follows the Ornstein-Uhlenbeck process

<span id="page-8-3"></span>
$$dv_t^a = \kappa^a \left( \bar{v}^a - v_t^a \right) dt + \sigma_v^a dW_t^v , \qquad (7)$$

and

<span id="page-9-1"></span>
$$dv_t^b = \kappa^b \left( \bar{v}^b - v_t^b \right) dt + \sigma_v^b \sqrt{v_t^b} dW_t^v, \tag{8}$$

see Heston (1993).

#### Fill ratio: orders with no discretion to walk the LOB

The fill ratio of MOsLP (buy and sell) with no discretion to walk the LOB is denoted by  $F = (F_t)_{\{0 \le t \le T\}}$  and satisfies the SDE

<span id="page-9-0"></span>
$$dF_t = \left(\lambda \left(\bar{F} - F_t^{\delta}\right) - h(v_t)\right) dt + \sigma_F dW_t^F.$$
(9)

Here, the function  $h: \mathbb{R}_+ \to \mathbb{R}$  describes the effect of the volatility of the micro-exchange rate on the fill ratio of the trader's strategy. The parameter  $\lambda > 0$  is the exponential speed at which the fill rate reverts to the level  $\bar{F} \in \mathbb{R}$ , the dispersion parameter  $\sigma_F$  is a non-negative constant, and  $W^F = (W_t^F)_{\{0 \le t \le T\}}$  is a standard Brownian motion uncorrelated to  $W^v$ . Recall that we propose three ways to compute fill ratios, see (1), (2), (3), so here F refers to one of those choices.

The parameters  $\lambda$ ,  $\bar{F}$ ,  $\sigma^F$ , and the function h(v) are specific to each trader in the FX market. Latency and type of liquidity taking strategy are the key characteristics that make the fill ratio dynamics specific to each trader. For example, the dynamics of the fill ratio for a trader with zero latency are as in (9) with parameters  $\sigma_F = 0$ ,  $\lambda > 0$ ,  $\bar{F} = 1$ , and the function h = 0.

The term  $\sigma^F dW^F$  represents the combined effect of two sources of uncertainty in the dynamics of the fill ratio, both of which depend on latency. One, the volatility of the micro-exchange rate will affect fill ratios via the function h(v) in (9). Two, between the time the trader is streamed quotes and the time the exchange receives the trader's MOLP, the LOB will have processed instructions from other market participants, hence the fill of the order is uncertain.

#### Fill ratio: orders with discretion to walk the LOB

Liquidity takers acknowledge that however fast their computers are, or efficient their software is, or whether their hardware is co-located, the time to reach the market and execute orders is not zero. A trading strategy in which market orders aim at only the best bid or best ask prices in the LOB will hardly deliver fill ratios of 100%.

One alternative to compensate for not reaching the market in time is to specify a maximum (minimum) price the trader is willing to pay (receive) when sending a MOLP. As discussed above, the price limit consists of the best offer (resp. bid) price observed by the trader plus (resp. minus) the discretion  $\delta$ . This discretion is the additional slippage she is willing to incur to fill the trade – the discretion to walk the LOB does not preclude the strategy from benefiting from price improvements. For example, if the trader sees the bid (ask) exchange rate at 1.000, then an immediate-execution limit sell (buy) order with discretion  $\delta = 0.001$  will be filled by the exchange with limit buy (sell) orders resting in the LOB down (up) to a minimum (maximum) bid (offer) price of 0.999 (1.001).

When the trader includes positive discretion in her MOsLP she will exert upward pressure on the fill ratio of her strategy because the order can walk the LOB. Thus, we assume that the trader's fill ratio, denoted by the controlled process  $F^{\delta} = (F_t^{\delta})_{\{0 \le t \le T\}}$ , follows the SDE

<span id="page-10-0"></span>
$$dF_t^{\delta} = \left(\lambda \left(\bar{F} - F_t^{\delta}\right) + g(\delta_t) - h(v_t)\right) dt + \sigma_F dW_t^F, \tag{10}$$

where the function  $g : \mathbb{R} \to \mathbb{R}$  models the impact of discretion on the fill ratio – when g = 0 we obtain (9).

In the sequel, we assume the impact functions are of the form

$$g(\delta) = a \delta$$
 and  $h(v) = b(v - \bar{v})$ ,

with a and b non-negative constants.

As usual, we work on a completed filtered probability space  $(\Omega, \mathbb{F}, (\mathcal{F}_t)_{t\geq 0}, \mathbb{P})$ , with  $\mathcal{F}_t$  the natural filtration generated by the 2-dimensional Brownian motion  $\mathbf{W} = (W^F, W^v)$ , and we refer to  $\mathbb{P}$  as the trader's reference measure.

### 4.1. Model uncertainty

The trader acknowledges that the model of fill ratios (10) may be misspecified, so she considers alternative dynamics of the fill ratio to make the model robust to misspecification, see Cartea et al. (2017). This ambiguity about model choice, or model uncertainty, affects the optimal strategy, i.e., affects the discretion of the orders she sends to the exchange. We incorporate the trader's ambiguity about model choice in two steps. First, we characterize alternative measures that describe the fill ratio dynamics considered by the trader, and then we determine how the trader chooses the reference measure  $\mathbb P$  or one of the alternative measures.

The trader considers candidate measures  $\mathbb{Q}(x)$  that are equivalent to  $\mathbb{P}$  and characterized by the Radon-Nikodym derivative

<span id="page-10-2"></span>
$$\frac{\mathrm{d}\mathbb{Q}(\boldsymbol{x})}{\mathrm{d}\mathbb{P}}\Big|_{t} = \exp\left\{-\frac{1}{2} \int_{0}^{t} \boldsymbol{x}'_{u} \, \boldsymbol{x}_{u} \, \mathrm{d}u - \int_{0}^{t} \boldsymbol{x}_{u} \, \mathrm{d}\boldsymbol{W}_{u}\right\},\tag{11}$$

where  $\boldsymbol{x}_t = (x_t^F, 0)$  is a two-dimensional  $\mathcal{F}_t$ -adapted process such that  $\left(d\mathbb{Q}(\boldsymbol{x})/d\mathbb{P}\Big|_t\right)_{0 \le t \le T}$  is a martingale. Thus, we denote by  $\boldsymbol{\mathcal{Q}}$  the class of alternative measures

$$\mathbf{\mathcal{Q}} = \left\{ \mathbb{Q}(\mathbf{x}) \mid \mathbf{x} \text{ is } \mathbf{\mathcal{F}} - \text{adapted and } \left( \frac{d\mathbb{Q}(\mathbf{x})}{d\mathbb{P}} \Big|_{t} \right)_{0 \le t \le T} \text{ is a martingale} \right\}.$$

Next, the trader penalizes deviations from the reference measure using the relative entropy from t to T, which is given by

<span id="page-10-1"></span>
$$\mathcal{H}_{t,T}\left(\mathbb{Q}\,|\,\mathbb{P}\right) = \frac{1}{\varphi}\,\log\left(\frac{\mathrm{d}\mathbb{Q}/\mathrm{d}\mathbb{P}\,|_{T}}{\mathrm{d}\mathbb{Q}/\mathrm{d}\mathbb{P}\,|_{t}}\right). \tag{12}$$

Here the parameter  $\varphi$  is a non-negative constant that represents the trader's degree of ambiguity aversion. If the trader is confident about the reference measure  $\mathbb{P}$ , then the ambiguity aversion parameter  $\varphi$  is small and any deviation from the reference model of fill dynamics is very costly. In the extreme  $\varphi \to 0$ , the trader is very confident about the reference measure, so she chooses  $\mathbb{P}$  because the penalty that results from rejecting the reference measure is too high. On the other hand, if the trader is very ambiguous about the reference model, considering alternative models results in a very small penalty. In the extreme  $\varphi \to \infty$ , deviations from the reference model are costless, so the trader considers the worst case scenario.

#### 4.2. Value function

The trader's value function is

$$V(t, f, v) = \sup_{\delta \in \mathcal{A}_{t,T}} \inf_{\mathbb{Q} \in \mathbf{Q}} \mathbb{E}_{t,f,v}^{\mathbb{Q}} \left[ -\phi_{\delta} \int_{t}^{T} \left( \delta_{s} - \hat{\delta} \right)^{2} ds - \phi_{F} \int_{t}^{T} \left( F_{s}^{\delta} - \hat{F} \right)^{2} ds + \mathcal{H}_{t,T} \left( \mathbb{Q} \mid \mathbb{P} \right) \right],$$

$$(13)$$

where  $\hat{F}$  denotes the target fill ratio and  $\hat{\delta}$  is a constant that denotes a fixed discretion to target. The last term on the right-hand side of the value function is the penalty (12).

Recall that the control variable  $\delta$  denotes the discretion of the order to walk the LOB, which is measured from the best quote observed by the trader when receiving the quotes from the exchange. The penalty parameters  $\phi_{\delta}$  and  $\phi_{F}$  are non-negative constants. For large values of the parameter  $\phi_{F}$  the optimal discretion will be larger for a higher target ratio  $\hat{F}$ .

Finally, recall that Q represents all the measures equivalent to the reference measure  $\mathbb{P}$ , and the set of admissible strategies is

$$\mathcal{A}_{0,T} = \left\{ \delta = (\delta_t)_{\{0 \le t \le T\}} \mid \delta \text{ is } \mathcal{F} - \text{adapted, } \mathbb{E}\left[\int_0^T (\delta_s)^2 \, \mathrm{d}s\right] < \infty, \text{ and}$$
 (14)

<span id="page-11-1"></span><span id="page-11-0"></span>
$$\delta_t = \mu\left(t, F_t^{\delta}, v_t\right), \text{ for } \mu \in \mathcal{M}_{0,T}\right\}, \qquad (15)$$

where

$$\mathcal{M}_{0,T} = \left\{ \mu : [0, T] \times \mathbb{R} \times \mathbb{R} \mapsto \mathbb{R} \mid \exists K \in \mathbb{R} \text{ s.t. } \forall \boldsymbol{x}, \, \boldsymbol{y} \in \mathbb{R}^2 \text{ and } t \in [0, T] \right.$$
$$\left| \mu(t, \boldsymbol{x}) - \mu(t, \boldsymbol{y}) \right| \leq K \left. |\boldsymbol{x} - \boldsymbol{y}| \text{ and } \left. |\mu(t, \boldsymbol{x})|^2 \leq K^2 \left( 1 + |\boldsymbol{x}|^2 \right) \right. \right\}. \tag{16}$$

We require the set of admissible strategies to satisfy the condition appearing in (15), so that the change of measure specified by (11) is valid.

By standard results, the Hamilton-Jacobi-Bellman-Isaacs (HJBI) equation associated to problem [\(13\)](#page-11-1) is given by

$$V_{t} + \sup_{\delta} \inf_{x} \left( \left( \lambda \left( \bar{F} - f \right) + a \, \delta - b \left( v - \bar{v} \right) - \sigma_{F} \, x \right) V_{f} + \frac{1}{2} \, \sigma_{F}^{2} \, V_{ff} + \frac{1}{2 \, \varphi} \, x^{2} \right.$$

$$\left. + \kappa \left( \bar{v} - v \right) V_{v} + \frac{1}{2} \, v^{2} \, \sigma_{v}^{2} \, V_{vv} - \phi_{\delta} \, \left( \delta - \hat{\delta} \right)^{2} - \phi_{F} \, \left( f - \hat{F} \right)^{2} \right) = 0 \,, \tag{17}$$

with terminal condition <sup>V</sup> (T, f, v) <sup>=</sup> 0. Here, subscripts in the function <sup>V</sup> represent partial derivatives, for example, <sup>V</sup><sup>t</sup> <sup>=</sup> ∂V /∂t .

<span id="page-12-4"></span>Proposition 1. The supremum and infimum in HJBI [\(17\)](#page-12-0) are achieved (in feedback form) at

<span id="page-12-1"></span><span id="page-12-0"></span>
$$\delta^* = \hat{\delta} + \frac{a V_f}{2 \phi_{\delta}}, \quad and \quad x^* = \varphi \sigma_F V_f,$$

respectively.

Proof. Apply first order conditions to the supremum and infimum terms in [\(17\)](#page-12-0), and check second order conditions to verify that these are the maximizer and minimizer, respectively.

Substituting δ <sup>∗</sup> and x ∗ in [\(17\)](#page-12-0), the HJBI becomes

$$V_{t} + \left(\lambda \left(\bar{F} - f\right) - b\left(v - \bar{v}\right)\right) V_{f} + \frac{1}{2} \sigma_{F}^{2} V_{ff} + \frac{a^{2} V_{f}^{2}}{2 \phi_{\delta}} - \frac{1}{2} \varphi V_{f}^{2} \sigma_{F}^{2} + a \hat{\delta} V_{f} + \kappa \left(\bar{v} - v\right) V_{v} + \frac{1}{2} v^{2} \sigma_{v}^{2} V_{vv} - \phi_{F} \left(f - \hat{F}\right)^{2} = 0,$$

$$V(T, f, v) = 0.$$
(18)

By inspection of the PDE [\(18\)](#page-12-1) and its terminal condition, we propose the ansatz

<span id="page-12-2"></span>
$$V(t, f, v) = h_0(t) + h_1(t) f + h_2(t) f^2 + h_3(t) v + h_4(t) v^2 + h_5(t) f v,$$
(19)

which we substitute in equation [\(18\)](#page-12-1) and obtain a coupled system of ordinary differential equations (ODEs). The system of ODEs can be solved explicitly to obtain closed-form solutions for the deterministic functions h0, h1, h2, h3, h4, h5, see [Appendix A.1.](#page-29-0)

<span id="page-12-3"></span>Theorem 1. (Verification) Define the time-dependent deterministic functions <sup>g</sup>1, g2, g<sup>3</sup> <sup>∶</sup> [0, T] <sup>↦</sup> <sup>R</sup> as

$$g_1(t) = h_1(t) + 2\hat{F}h_2(t) + \bar{v}h_5(t), \qquad g_2(t) = -2h_2(t), \qquad g_3(t) = h_5(t),$$

and the ambiguity aversion parameter obeys the bound

$$\varphi \le \frac{1}{\sigma_F^2} \left( \frac{a^2}{\phi_\delta} + \frac{1}{2} \frac{\lambda^2}{\phi_F} \right).$$
13

Then, the optimal discretion to walk the LOB is

<span id="page-13-0"></span>
$$\delta_t^* = \hat{\delta} + \frac{a}{2\phi_{\delta}} \left( g_1(t) + g_2(t) \left( \hat{F} - F_t^{\delta^*} \right) + g_3(t) \left( v_t - \bar{v} \right) \right), \tag{20}$$

and

$$x_t^* = \varphi \, \sigma_F \left( h_1(t) + 2 \, h_2(t) \, F_t^{\delta} + h_5(t) \, v_t \right) \,, \tag{21}$$

are admissible controls and equation (19) is the trader's value function (13).

*Proof.* For the proof see Appendix A.6.

We explain the intuition of the terms appearing in the optimal discretion (20). The first term on the right-hand side of (20) is the target discretion  $\hat{\delta}$ . For example, if the trader imposes an arbitrarily large penalty on deviations from this discretion target, i.e., penalty parameter  $\phi_{\delta} \to \infty$ , then the optimal discretion  $\delta_t^* \to \hat{\delta}$ .

The second term,  $g_1(t)$ , is the time-dependent baseline level of discretion the trader posts when her fill ratio is close to the target  $\bar{F}$  and volatility is around its long-term level  $\bar{v}$ .

The third term,  $g_2(t)$   $(\hat{F} - F_t^{\delta})$ , adjusts the strategy if the fill ratio is not on target. The function  $g_2(t)$  is positive for t < T, so when the fill ratio is below (above) its target  $\hat{F}$  the discretion to walk the LOB is increased (decreased).

The last term of the optimal strategy shows how the optimal discretion depends on the volatility of the micro-exchange rate. The function  $g_3(t)$  is positive for t < T, so when volatility is higher (lower) than its long-term level, the strategy increases (decreases) the discretion of the MOsLP.

Throughout this paper we assume that the volatility of the micro-exchange rate follows (6). In Appendix A.2 we derive the optimal strategy when volatility follows (7) and (8). Furthermore, as a robustness check, in Section 6 we analyze the performance of the latency-optimal strategy for these two alternative volatility models.

#### <span id="page-13-1"></span>4.2.1. Infinite-horizon latency-optimal strategy

We also derive the latency-optimal strategy when  $T \to \infty$ . In Appendix A.5 we present the infinite-horizon value function of the trader, where the optimal control is

$$\delta_t^* = \hat{\delta} + \frac{a}{2\phi_\delta} \left( c_1 + c_2 \left( \hat{F} - F_t^{\delta^*} \right) + c_3 \left( v_t - \bar{v} \right) \right), \tag{22}$$

with  $c_1=k_1+2\,\hat{F}\,k_2,\;c_2=-2\,k_2,\;\mathrm{and}\;c_3=k_5,\;\mathrm{and}\;\mathrm{the\;constants}\;k_1,\;k_2,\;k_5\;\mathrm{are}\;k_1+k_2$ 

$$k_{2} = \begin{cases} \frac{2\lambda + \beta - \sqrt{(2\lambda + \beta)^{2} + 8\alpha_{1}\phi_{F}}}{4\alpha_{1}} & \text{if } \alpha_{1} > 0, \\ -\frac{\phi_{F}}{\beta + 2\lambda} & \text{if } \alpha_{1} = 0, \\ \frac{2\lambda + \beta + \sqrt{(2\lambda + \beta)^{2} + 8\alpha_{1}\phi_{F}}}{4\alpha_{1}} & \text{if } \alpha_{1} < 0, \end{cases}$$

$$k_{5} = \frac{2bk_{2}}{2k_{2}\alpha_{1} - \lambda - \kappa - \beta}, \qquad k_{1} = \frac{2\phi_{F}\hat{F} + \left(2b\bar{v} + 2\lambda\bar{F} + 2a\hat{\delta}\right)k_{2} + \kappa\bar{v}k_{5}}{\lambda + \beta - 2k_{2}\alpha_{1}},$$

where  $\alpha_1 = \frac{a^2}{\phi_{\delta}} - \varphi \, \sigma_F^2$ ,  $\beta > 0$  is a discount factor (see (A.9)), and

$$\varphi \leq \frac{1}{\sigma_F^2} \left( \frac{a^2}{\phi_\delta} + \frac{\left(2\,\lambda + \beta\right)^2}{8\,\phi_F} \right).$$

It is straightforward to check that  $c_2$  and  $c_3$  are positive, and  $k_2$  is continuous in  $\alpha$ . At the end of Section 6 we discuss the performance of the infinite-horizon strategy.

# <span id="page-14-0"></span>5. Estimation of model parameters

In this section we show how to estimate the parameters of the models of volatility and fill ratio.

Volatility parameters. We discretize the continuous-time volatility model (6) and write

<span id="page-14-1"></span>
$$\tilde{v}_i = \tilde{v}_{i-1} + \kappa \left( \bar{v} - \tilde{v}_{i-1} \right) \Delta + \sigma_v \, \tilde{v}_{i-1} \sqrt{\Delta} \, \epsilon_i \,, \tag{23}$$

where  $i \in \{1, 2, ..., N-1\}$ ,  $0 = t_1 < t_2 < ... < t_N = T$ , T = 1,  $t_i = iT/N$ ,  $\epsilon_i \sim \mathcal{N}(0, \sigma_v^2 \Delta)$ , and  $\Delta = T/N$ .

Assume  $\{\tilde{v}_i\}_{i\in\{1,2,\ldots,N-1\}}$  are positive and divide (23) by  $\tilde{v}_{i-1}$ , so that

$$\frac{\tilde{v}_i}{\tilde{v}_{i-1}} - 1 = -\kappa \, \Delta + \kappa \, \bar{v} \, \Delta \, \frac{1}{\tilde{v}_{i-1}} + \sigma_v \, \sqrt{\Delta} \, \epsilon_i \,,$$

which we write as the OLS problem

<span id="page-14-3"></span><span id="page-14-2"></span>
$$\mathbf{y} = \beta_0 \, \mathbf{1} + \beta_1 \, \mathbf{s} + \boldsymbol{\epsilon} \,. \tag{24}$$

Here  $\boldsymbol{y}$  is a (N-1)-dimensional vector containing the dependent variables with entries  $y_i = \tilde{v}_i/\tilde{v}_{i-1} - 1$ ,  $\boldsymbol{1}$  is an (N-1)-dimensional vector of ones,  $\beta_0$  and  $\beta_1$  are scalar parameters,  $\boldsymbol{s}$  is an (N-1)-dimensional vector containing the regressors  $s_i = 1/\tilde{v}_{i-1}$ , and  $\boldsymbol{\epsilon}$  is the vector of residuals with i.i.d. entries  $\epsilon_i \sim \mathcal{N}(0, \sigma_v^2 \Delta)$ .

To obtain parameter estimates for  $\beta_0$  and  $\beta_1$  we employ the volatility of the micro-exchange rate at 500 millisecond intervals (see subsection 3.2) and use a standard OLS routine to compute the parameter estimates  $\hat{\beta}_0$  and  $\hat{\beta}_1$ . Now, because  $\beta_0 = -\kappa \Delta$  and  $\beta_1 = \kappa \bar{v} \Delta$ , we obtain the estimates

$$\hat{\kappa} = -\hat{\beta}_0/\Delta$$
,  $\hat{v} = -\hat{\beta}_1/\hat{\beta}_0$ , and  $\hat{\sigma}_v = \sigma_\epsilon/\sqrt{\Delta}$ , (25)

where  $\sigma_{\epsilon}$  is the standard deviation of the residuals in (24).

Fill ratio parameters. We discretize the continuous-time fill ratio model (10) and write

$$\tilde{F}_{i} - \tilde{F}_{i-1} = \lambda \, \bar{F} \, \Delta + a \, \delta_{i-1} \, \Delta - \lambda \, \Delta \, \tilde{F}_{i-1} - b \, \left( \tilde{v}_{i-1} - \bar{v} \right) \, \Delta + \sigma_F \sqrt{\Delta} \, \eta_i \,, \tag{26}$$

where, as above,  $i \in \{1, 2, ..., N-1\}$ ,  $0 = t_1 < t_2 < ... < t_N = T$ , T = 1,  $t_i = iT/N$ ,  $\eta_i \sim \mathcal{N}(0, \sigma_n^2 \Delta)$ , and  $\Delta = T/N$ .

We write (26) as the OLS problem

<span id="page-15-1"></span>
$$\boldsymbol{z} = \gamma_0 \, \boldsymbol{1} + \gamma_1 \, \boldsymbol{u} + \gamma_2 \, \boldsymbol{w} + \gamma_3 \, \boldsymbol{r} + \boldsymbol{\eta} \,, \tag{27}$$

where the vector  $\boldsymbol{z}$  contains the dependent variables,  $\gamma_0$ ,  $\gamma_1$ ,  $\gamma_2$ , and  $\gamma_3$  are scalar parameters, the vectors  $\boldsymbol{u}$ ,  $\boldsymbol{w}$ ,  $\boldsymbol{r}$  are regressors, and  $\boldsymbol{\eta}$  is the vector of residuals with i.i.d. entries  $\eta_i \sim \mathcal{N}(0, \sigma_F^2 \Delta)$ .

To estimate the impact parameter a in (26) we compute the effect of the discretion  $\delta$  on fill ratios for the set of values  $\delta_t = 0, 1, 2, 3, 4, 5$ , as follows. Throughout the day we assume that all FoK trades sent by T1 included a fixed discretion to walk the LOB of  $\delta = 0$ , and then repeat the analysis assuming  $\delta = 1$ , and  $\delta = 2$ , and so on. This provides us with six scenarios with fixed discretion for the whole trading day. We employ LOB data to determine if the orders were filled and create six (N-1)-dimensional vectors  $\mathbf{z_0}$ ,  $\mathbf{z_1}$ ,  $\mathbf{z_2}$ ,  $\mathbf{z_3}$ ,  $\mathbf{z_4}$ ,  $\mathbf{z_5}$ , where each vector corresponds to each scenario with fixed discretion. Next, we pool all the data so that the dependent variable on the left-hand side of the regression and the regressors on the right-hand side are  $6 \times (N-1)$ -dimensional vectors. We run a standard OLS routine to compute the parameter estimates  $\hat{\gamma}_0$ ,  $\hat{\gamma}_1$ ,  $\hat{\gamma}_2$ , and  $\hat{\gamma}_3$ . Then, the parameters of the fill ratio dynamics are

$$\hat{\lambda} = -\hat{\gamma}_1/\Delta$$
,  $\hat{\bar{F}} = -\hat{\gamma}_1/\hat{\gamma}_0$ ,  $\hat{b} = -\hat{\gamma}_2/\Delta$ ,  $\hat{a} = \hat{\gamma}_3/\Delta$ ,  $\hat{\sigma}_F = \sigma_\eta/\sqrt{\Delta}$ , (28)

where  $\sigma_{\eta}$  is the standard deviation of the errors in (27). To estimate model parameters for T2 we proceed in the same way and use the definition of fill ratio (2) because T2 sends IoC orders to the exchange.

Table 2 shows parameter estimates for T1 for the trading day starting at 22:05 of 3 January 2017 and ending at 22:00 on 4 January 2017, which for simplicity we refer to as the trading day of 4 January 2017.

<span id="page-15-2"></span>

| Parameter | $\hat{\bar{v}}$ | $\hat{\kappa}$ | $\hat{\sigma}_v$ | $\hat{\lambda}$ | $\hat{\bar{F}}$ | $\hat{\sigma}_F$ | â      | $\hat{b}$ |
|-----------|-----------------|----------------|------------------|-----------------|-----------------|------------------|--------|-----------|
| Estimate  | 0.0073          | 12.3887        | 1.3894           | 58.7206         | 0.9331          | 0.1944           | 1.0027 | 527.44    |

Table 2: Parameter estimates for T1's model, 4 January 2017. All parameters are statistically significant.

# <span id="page-15-0"></span>6. Performance of strategy

<span id="page-15-3"></span>In this section we show the performance of the optimal discretion strategy developed above. In subsection 6.1 we employ two days of trading data for T1 to discuss features of the strategy. In subsection 6.2 we employ data during the period December 2016 to March 2017 to study the performance of the strategy for T1 and T2 and in subsection 6.3 we discuss the results of the infinite-horizon case and present robustness checks. Finally, in Section 7 we use trade data to infer the latency of T1 and calculate the shadow price of latency that T1 would be willing to pay to reduce her latency in the marketplace.

### 6.1. Stylized features of latency-optimal strategy

We showcase features of the strategy for T1. We employ parameter estimates for 4 January 2017 to compute the optimal discretion for the trading day 5 January 2007. During 5 January 2017, T1 sent 3,043 FoK orders (1,601 buys and 1,442 sells) to the exchange. All orders were sent with a discretion of  $\delta = 0$ , and due to latency, T1 missed 279 trades, thus the fill ratio for the whole day was  $F_{3403} = 90.83\%$ .

Had T1 employed the strategy developed here, the optimal discretion in the MOsLP would have been as depicted in the top panel of Figure 2 and would have attained a fill ratio of  $F_{3043}^{\delta^*} = 99.17\%$ , i.e., miss 25 out of the 3,043 trade attempts. Compared to the fill ratio of the suboptimal strategy  $\delta = 0$ , which we refer to as the naive strategy, the latency-optimal strategy would have filled 254 more trades at an average cost of 1.74 ticks – recall that one tick in the USD/JPY pair is  $10^{-3}$  JPY and that the naive and latency-optimal strategies receive the same price improvements. The average cost is calculated as the cost of filling the 254 trades, in JPY, divided by the total volume of currency pairs of the 254 trades, and then multiplied by  $10^3$  to express it in ticks. The bottom panel of the same figure shows the volatility of the micro-exchange rate. In the next subsection we analyze in more detail the costs incurred by the optimal strategy to fill missed trades.

![](_page_16_Figure_3.jpeg)

<span id="page-16-0"></span>Figure 2: Parameters are  $\hat{F} = 100\%$ ,  $\phi_{\delta} = 5 \times 10^{-5}$ ,  $\phi_{F} = 5$ ,  $\varphi = 10^{-3}$ , T = 5 days, and other model parameters are in Table 2.

The left-hand panel of Figure 3 shows a heatmap of the fill ratio  $F_{3043}^{\delta^*}$  (i.e., 5 January 2017) for a range of parameters  $\phi_F$  and  $\phi_\delta$ . We observe that when the penalty parameter  $\phi_\delta$  is low, the strategy obtains the highest fill ratios because the trader is more willing to bear the costs of walking the LOB, i.e., incur more slippage. In the heatmap we also show, with a star, the pair  $(\phi_\delta, \phi_F) = (5 \times 10^{-5}, 5)$  and  $\zeta = 0$  (see (4)), which are the parameters we use in the analysis of subsection 6.2.

The right-hand panel of the figure shows a heatmap of the average cost of the fill ratios attainable by the optimal strategy. The cost reported is the slippage of the order relative to T1's naive strategy.

![](_page_17_Figure_0.jpeg)

Figure 3: Fill ratio  $F_{3043}^{\delta^*}$  for 5 January 2017. Parameters are  $\varphi = 10^{-3}$ ,  $\hat{\delta} = 0$ ,  $\hat{F} = 100\%$ , T = 5 days, and other model parameters are in Table 2.

Finally, Figure 4 shows the fill ratio  $F_{3043}^{\delta^*}$  for the range  $\varphi \in [0, a^2/\phi_\delta \, \sigma_F^2)$  of the ambiguity aversion parameter when the trader employs the optimal discretion strategy. Recall that the higher  $\varphi$  is, the less confident the trader is about the dynamics of  $F^\delta$ . When  $\varphi \to a^2/\phi_\delta \, \sigma_F^2$  the trader has very little confidence in her model of fill ratios, so the optimal strategy is to send orders with higher discretion to the exchange – the ambiguity averse trader is more willing to bear slippage costs to ensure high fill ratios. In Appendix A.1 we discuss the optimal control when  $\varphi = a^2/\phi_\delta \, \sigma_F^2$  and  $a^2/\phi_\delta \, \sigma_F^2 < \varphi \le \frac{1}{\sigma_F^2} \left(\frac{a^2}{\phi_\delta} + \frac{1}{2} \, \frac{\lambda^2}{\phi_F}\right)$ .

![](_page_17_Figure_3.jpeg)

<span id="page-17-2"></span><span id="page-17-1"></span>Figure 4: Fill ratio for optimal strategy. Parameters are  $\phi_{\delta} = 5 \times 10^{-5}$ ,  $\phi_{F} = 5$ ,  $\hat{F} = 100\%$ , T = 5 days, and other model parameters are in Table 2.

# <span id="page-17-0"></span>6.2. Performance of strategy for traders T1 and T2

We employ trade data for T1 and T2 between 5 December 2016 and 31 March 2017 to analyze the performance of the latency-optimal strategy. For each trading day we use the parameter estimates from the previous day and volatility of the exchange rate to compute the optimal discretion (20) in Proposition 1; recall that the volatility is calculated over a ten-minute window. We use LOB information to determine if the orders sent with the optimal discretion  $\delta^*$  would have been filled, and if so, at what price(s).

For each day we employ the first 10 minutes of the trading day (22:05 to 22:15) to compute the first observation of volatility of the micro-exchange rate. The first fill ratio observation ( $F_{50}$  for T1 and  $F_{50}^{AV}$  for T2) is computed the first time there are 50 trades after 22:15. Throughout the period we study we employ 4,115 trades for T1 and 4,089 for T2 to compute the first observations of volatility and fill ratio for each trading day, and to estimate the parameters of the model for the first day we employ 2,339 trades for T1 and 772 for T2. Thus, the number of trades we employ to analyze the performance of the strategy is reduced to 110,458 for T1 and 63,268 for T2.

#### 6.2.1. Performance of latency-optimal strategy for T1

Tables 3 and 4 provide information of the costs that T1 would have incurred had she employed the latency-optimal strategy and shows the mark-to-market costs of going back to the exchange to complete missed trades using market orders that walk the LOB until the order is filled in full.

During the period 5 December to 31 March 2017, T1 attempted 110,458 trades, all with discretion  $\delta = 0$ , and, due to latency, missed 9,483 trades, and received 3,938,559 JPY in price improvements. Had T1 employed market orders with infinite discretion, the cost of filling the 9,483 trades would have been 8,914,046 JPY, see row (a) in Table 3.<sup>3</sup> The last two columns of the same row show the mark-to-market cost of market orders that walk the LOB 20ms and 100ms later to fill the 9,483 trades missed by the naive strategy – time is measured from the time-stamp recorded by the exchange when T1's order was received. For example, if T1 were to return to the market (20ms and 100ms later) to retry the missed trade using a market order that can walk the LOB until filled in full, then the costs to fill the 9,483 missed trades would have been 9,841,755 JPY and 12,158,945 JPY, respectively.

In rows (b) to (e) we show the performance of the latency-optimal strategy for discretion targets  $\hat{\delta} \in \{0, 1, 2, 3\}$ , respectively. For example, row (b) shows that a strategy with target discretion  $\hat{\delta} = 0$  would have filled 8,318 more trades than the naive strategy. The cost of filling the 8,318 trades is 6,528,965 JPY and the mark-to-market costs to fill these trades, with market orders 20ms and 100ms later, are 7,459,198 JPY and 9,601,222 JPY, respectively.

Table 4 presents the average costs of filling missed trades in ticks ( $10^{-3}$  JPY). Column 3 in row (a) shows that the average mark-to-market cost of market orders with no price limit to fill the 9,483 trades missed by the naive strategy is 2.11 ticks (i.e.,  $2.11 = 8,914,046/4,222 \times 10^3$ ). Row (b) shows that the average cost of filling 8,318 trades missed by the naive strategy, which were filled by the optimal strategy with discretion target  $\hat{\delta} = 0$ , would have been 1.76 ticks, and the mark-to-market cost to fill the 8,318 trades with market orders that walk the book until filled, submitted 20ms or 100ms later, is 2.01 or 2.58 ticks.

The last two columns in Table 4 show the 'excess cost' (in percentage terms relative to optimal strategy's attainable cost) of returning to the market, 20ms and 100ms later, to complete unfilled trades with market orders that walk the book until filled in full. For

<span id="page-18-0"></span><sup>&</sup>lt;sup>3</sup>A market order with infinite discretion walks the LOB until it is filled in full, that is, there is no price limit.

example, the costs of filling missed trades with market orders 20ms (100ms) later are between 13% and 14% (44% and 47%) more than the cost of filling them with the optimal strategy.

The costs of returning to the market to fill missed trades employing market orders with infinite discretion is, on average, greater than the costs of completing the trades, on the first attempt, employing the latency-optimal strategy. Thus, not only does the optimal strategy attain a very high fill ratio, it does it at a cost which is lower than the mark-to-market value of completing the trades on a second attempt. These savings justify the extra cost of optimally walking the LOB in the first trade attempt to achieve higher fill ratios than the fill ratios achieved by the naive strategy. Note that we are not imputing other costs that the trader may incur if a trade is not filled. For example, some trades could be one leg of a trade, which if not completed, will affect other trades or strategies, see Cartea et al. (2018).

<span id="page-19-0"></span>

|     |                                 | ľ              | Missed by naive                  | , filled by a | lternative str                  | ategies                          |
|-----|---------------------------------|----------------|----------------------------------|---------------|---------------------------------|----------------------------------|
|     |                                 | Extra<br>Fills | Extra<br>Volume ×10 <sup>6</sup> | Cost in JPY   | Cost<br>20ms later<br>in JPY    | Cost<br>100ms later<br>in JPY    |
| (a) | $\delta_t = \infty , \forall t$ | 9,483          | 4,222                            | 8,914,046     | 9,841,755                       | 12,158,945                       |
|     | $\delta^*$ Target               |                |                                  |               | $\delta_t = \infty , \forall t$ | $\delta_t = \infty ,  \forall t$ |
| (b) | $\hat{\delta} = 0$              | 8,318          | 3,718                            | 6,528,965     | 7,459,198                       | 9,601,222                        |
| (c) | $\hat{\delta} = 1$              | 8,603          | 3,839                            | 6,807,416     | 7,770,984                       | 9,959,191                        |
| (d) | $\hat{\delta} = 2$              | 8,758          | 3,906                            | 6,999,804     | 7,950,543                       | 10,185,240                       |
| (e) | $\hat{\delta} = 3$              | 8,938          | 3,982                            | 7,232,545     | 8,181,285                       | 10,447,450                       |

Table 3: Performance of optimal strategy for T1. The total number of trade attempts is 110,458. Costrelated quantities are in JPY. Parameters:  $\phi_{\delta} = 5 \times 10^{-5}$ ,  $\phi_{F} = 5$ ,  $\varphi = 10^{-3}$ ,  $\hat{F} = 100\%$ , and T = 5 days. Period is from 5 December 2016 to 31 March 2017, currency pair USD/JPY.

<span id="page-19-1"></span>

|     |                                 |                | Mi                       | ssed by naive                       | , filled by alter                    | rnative strategie:                                                               | S                              |
|-----|---------------------------------|----------------|--------------------------|-------------------------------------|--------------------------------------|----------------------------------------------------------------------------------|--------------------------------|
|     |                                 | Extra<br>Fills | Avg.<br>cost<br>in ticks | Avg. cost<br>20ms later<br>in ticks | Avg. cost<br>100ms later<br>in ticks | $\begin{array}{c} \text{Cost increase} \\ \textbf{20ms later} \\ \% \end{array}$ | Cost increase 100ms later $\%$ |
| (a) | $\delta_t = \infty , \forall t$ | 9,483          | 2.11                     | 2.33                                | 2.88                                 | 10%                                                                              | 36%                            |
|     | $\delta^*$                      |                |                          |                                     |                                      | $\delta_t = \infty, \forall t$                                                   | $\delta_t = \infty, \forall t$ |
|     | Target                          |                |                          |                                     |                                      |                                                                                  |                                |
| (b) | $\hat{\delta} = 0$              | 8,318          | 1.76                     | 2.01                                | 2.58                                 | 14%                                                                              | 47%                            |
| (c) | $\hat{\delta} = 1$              | 8,603          | 1.77                     | 2.02                                | 2.59                                 | 14%                                                                              | 46%                            |
| (d) | $\hat{\delta} = 2$              | 8,758          | 1.79                     | 2.04                                | 2.61                                 | 14%                                                                              | 46%                            |
| (e) | $\hat{\delta} = 3$              | 8,938          | 1.82                     | 2.05                                | 2.62                                 | 13%                                                                              | 44%                            |

Table 4: Performance of optimal strategy for T1. The total number of trade attempts is 110,458. Cost-related quantities are weighted by volume and expressed in ticks,  $10^{-3}$  JPY. The metrics in column 6 (resp. 7) are the proportional increase of the values in columns 5 and 6 (resp. 5 and 7) in Table 3. Parameters:  $\phi_{\delta} = 5 \times 10^{-5}$ ,  $\phi_{F} = 5$ ,  $\varphi = 10^{-3}$ ,  $\hat{F} = 100\%$ , and T = 5 days. Period is from 5 December 2016 to 31 March 2017, currency pair USD/JPY.

Table 5 shows the results of the optimal strategy arranged in volatility quartiles when the discretion target is  $\hat{\delta} = 0$ . As discussed above, when the micro-exchange rate is more volatile, the chances of missing trades are greater than when volatility is low because the LOB is undergoing many more updates. The optimal strategy developed here counterbalances the adverse effects of high volatility on fill ratios, so that in periods of high volatility, everything else being equal, the trader sends orders with more discretion to walk the book. The table shows that as volatility increases, the strategy maintains a stable level of fills, while T1's naive strategy misses more trades as volatility increases.

The last three columns in Table 5 show the cost of filling trades missed by T1's naive strategy that are filled by the optimal strategy with  $\hat{\delta}=0$ . The first of the last three columns shows the cost incurred by the optimal strategy to execute missed trades for each volatility quartile. The penultimate and last columns of the table show the cost of returning to the market to fill the missed trades with market orders that walk the LOB until they are filled. As discussed earlier, the cost incurred by the latency-optimal strategy to fill trades missed by the naive strategy are lower than the costs of returning to the market 20ms and 100ms later. The gap between the costs of returning to the market 20ms and 100ms later and the costs incurred by the optimal strategy widens as volatility increases.

<span id="page-20-0"></span>

|                                                                                |                               |                      |                     |                                   |                    | Missed by naive, filled by $\delta^*$ with $\hat{\delta} = 0$ |                                     |                                      |  |  |  |
|--------------------------------------------------------------------------------|-------------------------------|----------------------|---------------------|-----------------------------------|--------------------|---------------------------------------------------------------|-------------------------------------|--------------------------------------|--|--|--|
| $\begin{array}{c} \textbf{Volatility} \\ \textbf{Quartiles} \\ \% \end{array}$ | Trades<br>sent to<br>Exchange | Fills $\delta_t = 0$ | $\%$ 0, $\forall t$ | Fills $\delta_t^*$ , $\delta_t^*$ | $\hat{\delta} = 0$ | Avg.<br>cost<br>in ticks                                      | Avg. cost<br>20ms later<br>in ticks | Avg. cost<br>100ms later<br>in ticks |  |  |  |
| 0–25                                                                           | 27,615                        | 26,151               | 94.7%               | 27,274                            | 98.8%              | 1.61                                                          | 1.77                                | 2.02                                 |  |  |  |
| 25-50                                                                          | 27,614                        | 25,588               | 92.7%               | 27,303                            | 98.9%              | 1.73                                                          | 1.92                                | 2.20                                 |  |  |  |
| 50 - 75                                                                        | 27,615                        | 25,086               | 90.8%               | 27,339                            | 99.0%              | 1.67                                                          | 1.91                                | 2.49                                 |  |  |  |
| 75 - 100                                                                       | 27,614                        | 24,150               | 87.5%               | 27,377                            | 99.1%              | 1.88                                                          | 2.19                                | 3.04                                 |  |  |  |

Table 5: Performance of strategy in volatility quartiles for T1. Parameters:  $\phi_{\delta} = 5 \times 10^{-5}$ ,  $\phi_{F} = 5$ ,  $\varphi = 10^{-3}$ ,  $\hat{F} = 100\%$ , and T = 5 days. Ticks are  $10^{-3}$  JPY. Period is from 5 December 2016 to 31 March 2017, currency pair USD/JPY.

#### 6.2.2. Performance of optimal strategy: T2

We repeat the analysis of the performance of the strategy using T2's trades. Tables 6 and 7 are presented in the same format as Tables 3 and 4 respectively.

During the period 5 December 2016 to 31 March 2017, T2 attempted 63,268 IoC trades, all with discretion  $\delta = 0$ , and, due to latency, missed 7,038 trades, including partial misses. The cost of achieving better fill ratios using the optimal strategy (for various discretion targets  $\hat{\delta}$ ) is justified by the cost of returning to the exchange to fill missed trades 20ms or 100ms later with market orders with infinite discretion to walk the book. For example, had T2 employed the optimal strategy with discretion target  $\hat{\delta} = 0$ , only 755 trades would have been missed, as opposed to the 7,038 misses by the naive strategy. The average cost of filling the 6,283 trades missed by the naive strategy is 1.24 ticks, as opposed to 2.82 and 2.75 ticks, which are the mark-to-market costs of returning to the market 20ms and 100ms later.

<span id="page-21-0"></span>

|     |                                 |                             | Missed by               | naive, filled by                           | alternativ  | e strategies                   |                                 |
|-----|---------------------------------|-----------------------------|-------------------------|--------------------------------------------|-------------|--------------------------------|---------------------------------|
|     |                                 | Extra Fills (incl. partial) | Extra Fills (only full) | Extra<br>Volume ×10 <sup>6</sup><br>in JPY | Cost in JPY | Cost<br>20ms later<br>in JPY   | Cost<br>100ms later<br>in JPY   |
| (a) | $\delta_t = \infty , \forall t$ | 7,038                       | 7,038                   | 1,455                                      | 2,294,999   | 4,628,993                      | 4,455,516                       |
|     | $\delta^*$ Target               |                             |                         |                                            |             | $\delta_t = \infty, \forall t$ | $\delta_t = \infty , \forall t$ |
| (b) | $\hat{\delta} = 0$              | 6,283                       | 6,238                   | 1,320                                      | 1,634,888   | 3,727,171                      | 3,631,491                       |
| (c) | $\hat{\delta} = 1$              | 6,446                       | 6,411                   | 1,340                                      | 1,665,638   | 3,742,734                      | 3,649,011                       |
| (d) | $\hat{\delta} = 2$              | 6,548                       | 6,517                   | 1,354                                      | 1,667,995   | 3,801,813                      | 3,690,360                       |
| (e) | $\hat{\delta} = 3$              | 6,648                       | 6,627                   | 1,373                                      | 1,733,090   | 3,903,934                      | 3,795,341                       |

Table 6: Performance of optimal strategy for T2. The total number of trade attempts is 63,268. Cost-related quantities in ticks ( $10^{-3}$  JPY). Parameters:  $\phi_{\delta} = 5 \times 10^{-5}$ ,  $\phi_{F} = 5$ ,  $\varphi = 10^{-3}$ ,  $\hat{F} = 100\%$ , and T = 5 days. Period is from 5 December 2016 to 31 March 2017, currency pair USD/JPY.

<span id="page-21-1"></span>

|     |                                 |                             | Missed 1                 | by naive, fille                     | d by alternativ                      | e strategies                                                              |                                 |
|-----|---------------------------------|-----------------------------|--------------------------|-------------------------------------|--------------------------------------|---------------------------------------------------------------------------|---------------------------------|
|     |                                 | Extra Fills (incl. partial) | Avg.<br>cost<br>in ticks | Avg. cost<br>20ms later<br>in ticks | Avg. cost<br>100ms later<br>in ticks | $\begin{array}{c} \text{Growth} \\ \textbf{20ms later} \\ \% \end{array}$ | Growth<br>100ms later<br>%      |
| (a) | $\delta_t = \infty , \forall t$ | 7,038                       | 1.58                     | 3.18                                | 3.06                                 | 102%                                                                      | 94%                             |
|     | $\delta^*$ Target               |                             |                          |                                     |                                      | $\delta_t = \infty , \forall t$                                           | $\delta_t = \infty , \forall t$ |
| (b) | $\hat{\delta} = 0$              | 6,283                       | 1.24                     | 2.82                                | 2.75                                 | 128%                                                                      | 122%                            |
| (c) | $\hat{\delta} = 1$              | 6,446                       | 1.24                     | 2.79                                | 2.72                                 | 125%                                                                      | 119%                            |
| (d) | $\hat{\delta} = 2$              | 6,548                       | 1.23                     | 2.81                                | 2.73                                 | 128%                                                                      | 121%                            |
| (e) | $\hat{\delta} = 3$              | 6,648                       | 1.26                     | 2.84                                | 2.76                                 | 125%                                                                      | 119%                            |

Table 7: Performance of optimal strategy for T2. The total number of trade attempts is 63,268. Cost-related quantities are weighted by volume and expressed in ticks ( $10^{-3}$  JPY). The metrics in column 6 (resp. 7) are the growth of the values in columns 5 and 6 (resp. 5 and 7) in Table 3. Parameters:  $\phi_{\delta} = 5 \times 10^{-5}$ ,  $\phi_{F} = 5$ ,  $\varphi = 10^{-3}$ ,  $\hat{F} = 100\%$ , and T = 5 days. Period is from 5 December 2016 to 31 March 2017, currency pair USD/JPY.

Table 8 shows the results of the optimal strategy arranged in volatility quartiles when the discretion target is  $\hat{\delta} = 0$ . The interpretation is the same as that of Table 5 for T1. The cost incurred by the latency-optimal strategy to fill the trades missed by the naive strategy is lower than the costs of returning to the market 20ms and 100ms later. The gap between the costs of returning to the market 20ms and 100ms later and the costs incurred by the optimal strategy widen as volatility increases.

<span id="page-22-2"></span>

|                                                                                | Missed by naive, filled by $\delta^*$ with $\hat{\delta}$ |                                      |                                  |                                            |                                  |                              |                                     |                                      |  |  |  |
|--------------------------------------------------------------------------------|-----------------------------------------------------------|--------------------------------------|----------------------------------|--------------------------------------------|----------------------------------|------------------------------|-------------------------------------|--------------------------------------|--|--|--|
| $\begin{array}{c} \textbf{Volatility} \\ \textbf{Quartiles} \\ \% \end{array}$ | Trades<br>sent to<br>exchange                             | Fills $\delta_t = 0$ (incl. p        | - / -                            | Fills $\delta_t^*, \delta_t$ (incl. p      | $\%$ $\hat{\delta} = 0$ partial) | Avg.<br>cost<br>in ticks     | Avg. cost<br>20ms later<br>in ticks | Avg. cost<br>100ms later<br>in ticks |  |  |  |
| 0%-25%<br>25%-50%<br>50%-75%<br>75%-100%                                       | 15,817<br>15,817<br>15,817<br>15,817                      | 14,950<br>14,545<br>14,226<br>13,329 | 94.5%<br>92.0%<br>89.9%<br>84.3% | 15,658<br>  15,631<br>  15,629<br>  15,610 | 99.0%<br>98.8%<br>98.8%<br>98.7% | 0.94<br>1.12<br>1.25<br>1.86 | 1.90<br>2.72<br>2.75<br>3.51        | 1.87<br>2.68<br>2.92<br>3.31         |  |  |  |

Table 8: Performance of strategy in volatility quartiles for T2. Parameters:  $\phi_{\delta} = 5 \times 10^{-5}$ ,  $\phi_{F} = 5$ ,  $\varphi = 10^{-3}$ ,  $\hat{F} = 100\%$ , and T = 5 days. Period is from 5 December 2016 to 31 March 2017, currency pair USD/JPY.

### <span id="page-22-1"></span>6.3. Infinite-horizon strategy and robustness checks

**Infinite-horizon.** Tables A.17 and A.18, which are the analogues of Tables 3 and 4, in Appendix A.5 show the results of the latency-optimal strategy for the infinite-horizon case discussed in Subsection 4.2.1. The results are broadly the same as those obtained for T1's strategy discussed above, where we assume T = 5 days – in the interest of space we do not report the results for T2.

Robustness to volatility parameter estimates. In our set-up the investor makes her model of fill ratios robust to model misspecification. We also check the robustness of the performance of the latency-optimal to: (i) parameter uncertainty of the volatility model (6), and (ii) different models of the volatility of the micro-exchange rate.

To check robustness to parameter uncertainty in (6), we look at eight scenarios that result from shocking the parameter estimates  $\hat{\kappa}$ ,  $\hat{\bar{v}}$ ,  $\hat{\sigma_v}$ . The shocked parameters are:  $\hat{\kappa}^u = 1.2\,\hat{\kappa}$ ,  $\hat{\kappa}^d = 0.8\,\hat{\kappa}$ ,  $\hat{v}^u = 1.2\,\hat{v}$ ,  $\hat{v}^d = 1.2\,\hat{v}$ ,  $\hat{\sigma}^u_v = 1.2\,\hat{\sigma_v}$ , and  $\hat{\sigma}^d_v = 0.8\,\hat{\sigma_v}$ , where  $\hat{\kappa}$ ,  $\hat{v}$ ,  $\hat{\sigma_v}$  are the estimates we obtain with the methodology outlined in Section 5. Next, we compute the optimal strategy  $\delta^*$  with the eight triplets of parameters resulting from all combinations of  $(\hat{\kappa}, \hat{v}, \hat{\sigma_v}) \in \{\hat{\kappa}^d, \hat{\kappa}^u\} \times \{\hat{v}^d, \hat{v}^u\} \times \{\hat{\sigma_v}^d, \hat{\sigma_v}^u\}$ . In Appendix A.3.1 we report the results for  $\hat{\delta} = 0$ . We find that the fill ratios lie in the range 98.5% to 99% and the average tick cost is approximately 1.76 ticks in all cases.

Finally, we assume that the volatility of the micro-exchange rate follows (7) and (8) and compute the performance of the latency-optimal strategy, see Appendix A.4. We find that the results are broadly the same as those discussed above when volatility follows (6).

# <span id="page-22-0"></span>7. The cost of latency

One approach to mitigate the effects of latency on the efficacy of trading strategies is to invest on hardware and co-location services to reduce the time delays associated to the different components of the life cycle of a trade, see definition of latency in Section 2. As latency shortens, traders that aim at the best prices they observe in the LOB will be on target more often. This improvement in the marksmanship of the trader increases the fill ratio of the strategy, but also reduces the chances of receiving price improvements.

Another approach is to devise latency-optimal strategies that lessen the adverse effects of time delays, e.g., failing to complete trades. Although these strategies do not reduce time delays in the life cycle of trade, they are a substitute for cutting down latency when the objective is to increase the percentage of MOsLP that are filled.

Neither approach is free. The first approach requires the trader to pay fixed costs to operate in the marketplace with lower latency, which increases the efficacy of the MOsLP but reduces opportunities of obtaining price improvements. In the second approach, costs accrue to the strategy when MOsLP walk the LOB, while benefits accrue because the latency-optimal approach scoops price improvements when the market, due to latency, moves in the trader's interest.

In this section we compute the shadow price that T1 would be willing to pay to reduce her latency in the marketplace. We proceed as follows. i) Consider hypothetical traders who employ the same naive strategy (i.e., zero discretion to walk LOB) as that of T1, but each trader acts in the market with a different fixed latency – for simplicity we assume latency is not stochastic. ii) Compute the fill ratio achieved by each hypothetical trader's naive strategy. iii) Map levels of latency to fill ratios. iv) Find the hypothetical trader whose fill ratio is the same as that achieved by T1's latency-optimal strategy developed above, and compute the price improvements of the hypothetical trader's strategy. v) Compute the difference of the latency-optimal costs of walking the LOB and its price improvements. Thus, the difference between the costs in (iv) and (v) is the shadow price of latency that T1 would be willing to pay to employ a naive strategy (no discretion to walk LOB), which obtains the same fill ratio as that of the latency-optimal strategy.

# 7.1. Latency and fill ratios

Recall that the attributes we have for each order include: type of trade, volume of the trade, price limit, and direction (buy or sell) of the trade. We also have the time-stamp of when the order is processed by the exchange (this time is denoted by  $t_3$  in our discussion of latency in Section 2 above). However, we do not know the time it took the trader to process information and make a decision before instructing the exchange, or the time when the trader sent the orders to the exchange – all of which affect the latency of the trader in the marketplace.

To map latency to fill ratios we devise fifty hypothetical traders who are clones of T1. The only difference between T1 and the hypothetical traders is that each clone has a different latency in the market. We denote each hypothetical trader by  $T_j$  with  $j = 0, 1, 2, \dots, 50$ , and assume that the latency of  $T_j$  is jms, i.e.  $t_3 - t_0 = j$  ms. Note that although impossible for a trader to operate in the marketplace with a latency of 0ms, we include it in our list of hypothetical traders for comparison purposes.

In our approach we assume that the clones employ the same strategy as T1 regardless of their latency. However, this may not be the case because if T1's latency was lower than her actual latency, her trading strategy could be different from the one she employed during the period we analyze. For example, T1 may not be attempting potentially profitable trades because she acknowledges that her latency is too long to successfully complete trades that require more speed.

We use  $T_{10}$  to illustrate how we map a latency of 10ms to a measure of fill ratio – the fill ratio of the other hypothetical traders is calculated in the same way. The fill ratio is computed as the percentage of filled orders in one trading day – this coincides with definition  $F_n$ , provided in (1) with  $\zeta = 0$ , where n is the number of trades in the day. We assume that  $T_{10}$  replaces T1 in the market. Thus,  $T_{10}$  sends orders that have the same direction, volume, type (i.e., FoK), and discretion to walk the LOB, as those of T1, and assume the orders from  $T_{10}$  reach the LOB an instant before T1's trade was filled (for which we have a time-stamp), so the hypothetical trader and T1 face the same market conditions. Therefore, orders sent by  $T_{10}$  and T1 only differ in that  $T_{10}$  attempts to fill the trade at the best quote streamed by the exchange 10ms before the exchange receives the order.

For example, to compute the fill ratio that  $T_{10}$  would have obtained on 5 January 2017, we employ the time-stamps (when the exchange processes the order) of the 3,043 orders sent by T1 on that day and compute the fill ratio that  $T_{10}$  would have achieved. We repeat this approach for each hypothetical trader on the same day and depict the results in the left-hand panel of Figure 5. As expected, there is a (monotonic) decreasing relationship between latency and fill ratio. In one extreme, when latency is zero,  $T_0$  would have obtained a fill ratio of 100%. At the other extreme  $T_{50}$ 's fill ratio is 89%.

In the figure, the square marker shows the point where latency of 27ms is mapped to 90%, which is the fill ratio obtained by T1's naive strategy. The diamond marker in the upper-left corner of the figure shows the latency of a hypothetical trader who achieved a fill ratio of 99%. Note that this fill ratio corresponds (approximately) to the fill ratio T1 would have obtained ( $F_{3043}^{\delta^*} = 98.73\%$ ) had she employed the latency-optimal strategy with targets  $\hat{\delta} = 0$  and  $\hat{F} = 100\%$ . Thus, we say that, on 5 January 2017, T1's implied latency is 27ms and the implied latency of the optimal strategy is 3ms.

We repeat the analysis for each day between 5 December 2016 and 31 March 2017. The right-hand panel of Figure 5 shows the implied latencies of T1's naive strategy (solid line) and that of the latency-optimal strategy with target  $\hat{\delta} = 0$  (dotted line). The variations in 'implied' latency are due to a number of factors, including the volatility of the best quotes which, as discussed above, has a considerable effect on fill ratios. For ease of presentation the y-axis is capped at 50ms – there were two days when T1's implied latency was over 50ms.

![](_page_25_Figure_0.jpeg)

<span id="page-25-0"></span>![](_page_25_Figure_1.jpeg)

Figure 5: Left-hand panel: Map of latency to fill ratio employing T1's trade time-stamps and LOB information on 5 January 2017. Square marker is T1's implied latency. Diamond marker is the implied latency of the optimal strategy. Right-hand panel: implied latency for T1 and implied latency for latency-optimal strategy employing T1's trade time-stamps and LOB information during the period 5 December 2016 to 31 March 2017.

Table [9](#page-25-1) summarizes the results. The top panel of the table shows the mean, standard deviation, and median of the latency implied by the naive strategy and by the latencyoptimal strategies with various discretion targets ˆδ. The bottom panel provides summary statistics of the daily fill ratio obtained by the strategies. Here, the fill ratio F<sup>N</sup> refers to the percentage of orders that were filled each day, and the table shows the mean, standard deviation, and median of the daily percentage of fills. For the latency-optimal strategy the mean fill is between 98.9% and 99.5% and for T1's naive strategy the mean fill is 91.0%. We observe that the standard deviation of the fill ratio of the optimal strategy is also considerably lower than that of the naive strategy. Therefore, the optimal strategy achieves much higher fill ratios than the naive strategy, and produces more stable results because the optimal strategy depends on the volatility of the micro-exchange rate.

<span id="page-25-1"></span>

|         | Naive<br>strategy |        | ∗<br>Optimal Strategy δ<br>Target |        |        |      |  |  |  |  |
|---------|-------------------|--------|-----------------------------------|--------|--------|------|--|--|--|--|
|         |                   | δˆ = 0 | δˆ = 1                            | δˆ = 2 | δˆ = 3 | ∀t   |  |  |  |  |
| Latency |                   |        |                                   |        |        |      |  |  |  |  |
| mean    | 20.02             | 2.34   | 2.01                              | 1.70   | 1.53   | 0    |  |  |  |  |
| std     | 11.31             | 1.72   | 1.57                              | 0.89   | 0.80   | 0    |  |  |  |  |
| median  | 18.00             | 2.00   | 2.00                              | 1.00   | 1.00   | 0    |  |  |  |  |
| FN      |                   |        |                                   |        |        |      |  |  |  |  |
| mean    | 91.9%             | 98.9%  | 99.2%                             | 99.3%  | 99.5%  | 100% |  |  |  |  |
| std     | 2.9%              | 0.4%   | 0.4%                              | 0.4%   | 0.3%   | 0%   |  |  |  |  |
| median  | 92.2%             | 98.9%  | 99.2%                             | 99.4%  | 99.5%  | 100% |  |  |  |  |

Table 9: Implied latency for T1. Period is 5 December 2016 to 31 March 2017, currency pair USD/JPY.

# 7.2. Shadow price of latency

The shadow price of latency is the price that T1 would be willing to pay to reduce her latency, so a naive and the latency-optimal strategies obtain the same fill ratio. To compute this price we need: Latency-optimal cost of walking the LOB and price improvements, (ii) price improvements received by the hypothetical trader with latency equal to that implied by the latency-optimal strategy.

For example, on 5 January 2017, the latency-optimal strategy incurs 92,771 JPY in costs from walking the LOB and receives 69,305 JPY in price improvements. On the other hand, the naive strategy of the hypothetical trader with latency 3ms, receives 7,592 JPY in price improvements. Thus, on 5 January 2017, T1 would be willing to pay 31,058 JPY to reduce her latency from 22ms to 3ms. We repeat the analysis for all trading days between 5 December 2016 and 31 March 2017 and compute T1's shadow price of latency for each day. Table [10](#page-26-1) contains summary statistics of the results.

The table shows that T1 would be willing to pay approximately 3⋅10<sup>6</sup> JPY (around 30,000 USD) to reduce her latency from 20.02ms to 2.34ms. The upper bound of approximately <sup>5</sup> <sup>⋅</sup> <sup>10</sup><sup>6</sup> JPY (around 50,000 USD) for the shadow price of latency is given by the last column and last row of the table, where we show the costs of always employing market orders. These shadow prices are, according to market participants, lower than co-location, hardware, and other costs that traders would have to incur to reduce latency in the life cycle of a trade.

<span id="page-26-1"></span>

|                                | Naive<br>strategy |           |           | ∗<br>Optimal Strategy δ<br>Target |           |           |  |  |
|--------------------------------|-------------------|-----------|-----------|-----------------------------------|-----------|-----------|--|--|
|                                |                   | δˆ = 0    | δˆ = 1    | δˆ = 2                            | δˆ = 3    | ∀t        |  |  |
| Implied Latency (ms)           | 20.02             | 2.34      | 2.01      | 1.70                              | 1.53      | 0         |  |  |
| Walk LOB Cost                  | 0                 | 6,528,965 | 6,807,416 | 6,999,804                         | 7,232,545 | 8,914,046 |  |  |
| Price Improvement              | 3,938,559         | 3,938,559 | 3,938,559 | 3,938,559                         | 3,938,559 | 3,938,559 |  |  |
| Price Improvement              |                   |           |           |                                   |           |           |  |  |
| with Reduced Latency           | 3,938,559         | 384,035   | 291,070   | 179,875                           | 135,744   | 0         |  |  |
| Shadow Price to Reduce Latency | 0                 | 2,974,441 | 3,159,927 | 3,241,120                         | 3,429,730 | 4,975,487 |  |  |

Table 10: Shadow price to reduce latency reported in JPY. Period is 5 December 2016 to 31 March 2017, currency pair USD/JPY.

# <span id="page-26-0"></span>8. Conclusions

In this paper, we showed how to compute the price that FX traders are willing to pay to reduce their latency in the marketplace. To achieve this we developed a latency-optimal strategy to map the costs of the strategy to a reduction in latency.

In particular, we employed a set of proprietary data of FX transactions to show how latency affects the percentage of liquidity taking orders filled by a trader's strategy. We analyzed the trades of two liquidity takers over a four-month period and showed that approximately 10% of their orders were not filled due to latency.

To calculate the shadow price of latency of traders we derived a strategy that specifies the limit price of the market orders sent to the exchange. The price limit for each liquidity taking order balances the tradeoff between the costs from walking the LOB and how far is the fill ratio from the trader's desired target. The trader's optimal strategy specifies the price limit for each transaction depending on the proportion of orders that have been filled, how far is the strategy from the target fill ratio, the cost of walking the LOB, and the volatility of the exchange rate. For example, everything else being equal, the optimal price limit to walk the LOB is higher (resp. lower) when the volatility of the exchange rate is above (resp. below) its long-term level.

We showed the performance of the latency-optimal strategy using trade data for two FX traders. We computed the costs incurred by the latency-optimal strategy to increase fill ratios and showed that the costs of the strategy are lower than the costs of returning to the market 20ms or 100ms later to fill a missed trade. Moreover, we showed that the latency-optimal strategy obtains similar fill ratios for different levels of volatility. This is in contrast to the performance of the naive strategy where the majority of the missed trades occur when the volatility of the exchange rate is high.

Finally, we employed the proprietary data set to build a function that maps latency of traders to fill ratios. We used this mapping to compute the shadow price of latency that traders are willing to pay to reduce latency in the marketplace. We computed the shadow price a particular trader is willing to pay to reduce her latency by investing in hardware, co-location, and other services. Our results showed that the trader would be better off employing the latency-optimal strategy developed here, instead of investing in hardware and co-location services to reduce latency.

# References

<span id="page-27-4"></span>Almgren, R. (2012). Optimal trading with stochastic liquidity and volatility. SIAM Journal on Financial Mathematics, 3(1):163–181.

<span id="page-27-2"></span>Barger, W. and Lorig, M. (2018). Optimal liquidation under stochastic price impact. arXiv preprint arXiv:1804.04170.

<span id="page-27-1"></span>Bayraktar, E. and Ludkovski, M. (2010). Optimal trade execution in illiquid markets. Mathematical Finance, 21(4):681–701.

<span id="page-27-5"></span>Cartea, A., Donnelly, R., and Jaimungal, S. (2017). Algorithmic trading with model uncertainty. ´ SIAM Journal on Financial Mathematics, 8(1):635–671.

<span id="page-27-3"></span>Cartea, A., Jaimungal, S., and Penalva, J. (2015). ´ Algorithmic and High-Frequency Trading. Cambridge University Press.

<span id="page-27-6"></span>Cartea, A., Jaimungal, S., and Walton, J. (2018). Foreign exchange markets with Last Look. ´ Mathematics and Financial Economics (forthcoming).

<span id="page-27-7"></span>Cheridito, P., Filipovi´c, D., and Kimmel, R. L. (2007). Market price of risk specifications for affine models: Theory and evidence. Journal of Financial Economics, 83(1):123 – 170.

<span id="page-27-0"></span>Gould, M. D., Porter, M. A., and Howison, S. D. (2016). The long memory of order flow in the foreign exchange spot market. Market Microstructure and Liquidity, 02(01):1650001.

- <span id="page-28-3"></span>Gu´eant, O. (2016). The financial mathematics of market liquidity: From optimal execution to market making, volume 33. CRC Press.
- <span id="page-28-4"></span>Heston, S. L. (1993). A closed-form solution for options with stochastic volatility with applications to bond and currency options. The Review of Financial Studies, 6.
- <span id="page-28-2"></span>Lehalle, C.-A. and Mounjid, O. (2017). Limit order strategic placement with adverse selection risk and the role of latency. Market Microstructure and Liquidity, 03(01):1750009.
- <span id="page-28-0"></span>Moallemi, C. C. and Saˆglam, M. (2013). The cost of latency in high-frequency trading. Operations Research, 61(5):1070–1086.
- <span id="page-28-1"></span>Stoikov, S. and Waeber, R. (2016). Reducing transaction costs with low-latency trading algorithms. Quantitative Finance, 16(9):1445–1451.

# Appendix A.

# <span id="page-29-0"></span>Appendix A.1. System of ODEs satisfied by ansatz

Insert ansatz (19) into HJBI (18) and collect terms to obtain the following coupled system of six ODEs:

$$h_0'(t) + (b\bar{v} + a\hat{\delta} + \lambda\bar{F})h_1(t) + \sigma_F^2h_2(t) + \kappa\bar{v}h_3(t) + \frac{1}{2}\left(\frac{a^2}{\phi_\delta} - \varphi\sigma_F^2\right)(h_1(t))^2 - \phi_F\hat{F}^2 = 0, \quad (A.1)$$

$$h'_{1}(t) + (2b\bar{v} + 2\lambda\bar{F} + 2a\hat{\delta})h_{2}(t) - \lambda h_{1}(t) + \kappa\bar{v}h_{5}(t) + 2\left(\frac{a^{2}}{\phi_{\delta}} - \varphi\sigma_{F}^{2}\right)h_{1}(t)h_{2}(t) + 2\phi_{F}\hat{F} = 0,$$
(A.2)

$$h_2'(t) - 2\lambda h_2(t) + 2\left(\frac{a^2}{\phi_\delta} - \varphi \sigma_F^2\right) (h_2(t))^2 - \phi_F = 0,$$
 (A.3)

$$h_3'(t) - b h_1(t) + (b \bar{v} + a \hat{\delta} + \lambda \bar{F}) h_5(t) + 2 \kappa \bar{v} h_4(t) - \kappa h_3(t) + \left(\frac{a^2}{\phi_{\delta}} - \varphi \sigma_F^2\right) h_1(t) h_5(t) = 0, \quad (A.4)$$

$$h_4'(t) - bh_5(t) + (\sigma_v^2 - 2\kappa)h_4(t) + \frac{1}{2}\left(\frac{a^2}{\phi_\delta} - \varphi\,\sigma_F^2\right)(h_5(t))^2 = 0,$$
(A.5)

$$h_5'(t) - 2bh_2(t) - (\lambda + \kappa)h_5(t) + 2\left(\frac{a^2}{\phi_\delta} - \varphi \sigma_F^2\right)h_2(t)h_5(t) = 0,$$
(A.6)

with terminal conditions

$$h_0(T) = 0$$
,  $h_1(T) = 0$ ,  $h_2(T) = 0$ ,  $h_3(T) = 0$ ,  $h_4(T) = 0$ ,  $h_5(T) = 0$ .

Here the notation h'(t) is short-hand for dh(t)/dt. Next we provide solutions for  $h_2$ ,  $h_5$ , and  $h_1$ , which are the functions required to write the optimal control in closed-form.

#### Explicit solution for $h_2$ .

The function  $h_2$  satisfies the Riccati ODE in (A.3) with terminal condition  $h_2(T) = 0$  and its solution depends on the sign of the coefficient  $\varphi \sigma_F^2 - a^2/\phi_\delta$ . Therefore:

• Case 1:  $\varphi < a^2/\sigma_F^2 \phi_\delta$ , then

<span id="page-29-1"></span>
$$h_2(t) = c_1 \tanh(c_2 t + c_3) + c_4$$

with

$$\alpha_1 = \frac{a^2}{\phi_\delta} - \varphi \, \sigma_F^2, \quad c_1 = \frac{c_2}{2 \, \alpha_1}, \quad c_2 = -\sqrt{2 \, \alpha_1 \, \phi_F + \lambda^2},$$

$$c_3 = \operatorname{atanh}\left(-\frac{\lambda}{c_2}\right) + T \sqrt{2 \, \alpha_1 \, \phi_F + \lambda^2}, \quad c_4 = \frac{\lambda}{2 \, \alpha_1}.$$

• Case 2:  $\varphi = a^2/\sigma_F^2 \phi_\delta$ , then

$$h_2(t) = \frac{\phi_F}{2\lambda} \left( e^{-2\lambda (T-t)} - 1 \right).$$

• Case 3: 
$$a^2/\sigma_F^2 \phi_\delta < \varphi \le \frac{1}{\sigma_F^2} \left( \frac{a^2}{\phi_\delta} + \frac{1}{2} \frac{\lambda^2}{\phi_F} \right)$$
, then

$$h_2(t) = \tilde{c}_1 \tan(\tilde{c}_2 t + \tilde{c}_3) + \tilde{c}_4,$$

with

$$\tilde{\alpha}_{1} = \varphi \, \sigma_{F}^{2} - \frac{a^{2}}{\phi_{\delta}}, \quad \tilde{c}_{1} = \frac{\tilde{c}_{2}}{2 \, \tilde{\alpha}_{1}}, \quad \tilde{c}_{2} = -\sqrt{2 \, \tilde{\alpha}_{1} \, \phi_{F} - \lambda^{2}},$$

$$\tilde{c}_{3} = -\operatorname{atan}\left(-\frac{\lambda}{\tilde{c}_{2}}\right) + T \, \sqrt{2 \, \tilde{\alpha}_{1} \, \phi_{F} - \lambda^{2}}, \quad \tilde{c}_{4} = \frac{\lambda}{2 \, \tilde{\alpha}_{1}}.$$

We use the integrating-factor technique to write

$$h_5(t) = -e^{\int_t^T (2\alpha_1 h_2(u) - \kappa - \lambda) du} \int_t^T 2b h_2(s) e^{-\int_s^T (2\alpha_1 h_2(u) - \kappa - \lambda) du} ds$$

and similarly we write

$$h_1(t) = e^{\int_t^T (2\alpha_1 h_2(u) - \lambda) du} \int_t^T (\kappa \, \bar{v} \, h_5(s) + e_1 \, h_2(s) + e_2) \, e^{-\int_s^T (2\alpha_1 h_2(u) - \lambda) du} \, ds$$

where  $e_1 = 2b\bar{v} + 2\lambda\bar{F} + 2a\hat{\delta}$  and  $e_2 = 2\phi_F\hat{F}$ .

From now on we focus on Case 1 to obtain closed-form formulae for  $h_5$  and  $h_1$ ; Cases 2 and 3 are similar.

**Explicit solution for**  $h_5$ . Function  $h_5$  can be explicitly written as

$$h_5(t) = -\frac{e^{-\kappa(T-t)}}{\cosh(t c_2 + c_3)} \times \left[ \left( \frac{e^{d_2(T-t) + d_3} - e^{d_3}}{d_2} \right) b(c_1 + c_4) + \left( \frac{e^{d_1(T-t) - d_3} - e^{-d_3}}{d_1} \right) b(c_4 - c_1) \right],$$

where the constants  $d_1 = \kappa + c_2$ ,  $d_2 = \kappa - c_2$ , and  $d_3 = c_3 + T c_2$ .

**Explicit solution for**  $h_1$ . Function  $h_1$  can be solved explicitly to obtain

$$h_1(t) = \frac{-\kappa \bar{v}}{\cosh(c_2 t + c_3)}$$

$$\times \left[ \frac{b(c_1 + c_4) e^{d_3}}{d_2} \left( \frac{e^{-\kappa (T - t)} - 1}{\kappa} - \frac{e^{-c_2 (T - t)} - 1}{c_2} \right) + \frac{b(c_4 - c_1) e^{-d_3}}{d_1} \left( \frac{e^{c_2 (T - t)} - 1}{c_2} + \frac{e^{-\kappa (T - t)} - 1}{\kappa} \right) \right]$$

$$+ \frac{e_1 c_1}{c_2 \cosh(c_2 t + c_3)} \left( \cosh(c_2 T + c_3) - \cosh(c_2 t + c_3) \right)$$

$$+ \frac{e_1 c_4 + e_2}{c_2 \cosh(c_2 t + c_3)} \left( \sinh(c_2 T + c_3) - \sinh(c_2 t + c_3) \right).$$

<span id="page-30-0"></span>Finally, the functions  $h_0$  and  $h_3$  are obtained explicitly in a similar way using an integrating factor technique. Note that to obtain the optimal controls explicitly we only require  $h_1$ ,  $h_2$ ,  $h_5$ .

# Appendix A.2. Alternative models for volatility

If we model the volatility of the micro-exchange rate with the Ornstein-Uhlenbeck process (7), then the trader's value function satisfies the HJBI

<span id="page-31-0"></span>
$$V_{t} + \sup_{\delta} \inf_{x} \left( \left( \lambda \left( \bar{F} - f \right) + a \, \delta - b \left( v - \bar{v}^{a} \right) - \sigma_{F} \, x \right) \, V_{f} + \frac{1}{2} \, \sigma_{F}^{2} \, V_{ff} + \frac{1}{2 \, \varphi} \, x^{2} \right.$$

$$\left. + \kappa^{a} \left( \bar{v}^{a} - v \right) V_{v} + \frac{1}{2} \, v^{2} \, \left( \sigma_{v}^{a} \right)^{2} \, V_{vv} - \phi_{\delta} \, \left( \delta - \hat{\delta} \right)^{2} - \phi_{F} \, \left( f - \hat{F} \right)^{2} \right) = 0 \, . \tag{A.7}$$

This HJBI is similar to (17), where the three parameters  $\kappa$ ,  $\bar{v}$ ,  $\sigma_v$  in (17) become  $\kappa^a$ ,  $\bar{v}^a$ ,  $\sigma_v^a$ , respectively, and the term  $\frac{1}{2} v^2 \sigma_v^2 V_{vv}$  becomes  $\frac{1}{2} (\sigma_v^a)^2 V_{vv}$ .

Clearly, the optimal controls that result from (A.7) have the same functional form as those we derived above in Proposition 1. To solve (A.7) we employ ansatz (19) and derive a system of ODEs similar to the one shown in Appendix A.1.

When we employ Heston's volatility model (8), the trader's value function satisfies the HJBI

<span id="page-31-1"></span>
$$V_{t} + \sup_{\delta} \inf_{x} \left( \left( \lambda \left( \bar{F} - f \right) + a \, \delta - b \left( v - \bar{v}^{b} \right) - \sigma_{F} \, x \right) V_{f} + \frac{1}{2} \, \sigma_{F}^{2} \, V_{ff} + \frac{1}{2 \, \varphi} \, x^{2} \right.$$

$$\left. + \kappa^{b} \left( \bar{v}^{b} - v \right) V_{v} + \frac{1}{2} \, v^{2} \left( \sigma_{v}^{b} \right)^{2} \, V_{vv} - \phi_{\delta} \left( \delta - \hat{\delta} \right)^{2} - \phi_{F} \left( f - \hat{F} \right)^{2} \right) = 0 \,. \tag{A.8}$$

As before, this HJBI is similar to (17), where the three parameters  $\kappa$ ,  $\bar{v}$ ,  $\sigma_v$  are now  $\kappa^b$ ,  $\bar{v}^b$ ,  $\sigma_v^b$ , and the term  $\frac{1}{2}v^2\sigma_v^2V_{vv}$ , is now  $\frac{1}{2}(\sigma_v^a)^2vV_{vv}$ .

The optimal controls that result from (A.8) have the same functional form as those we derived above in Proposition 1. In Appendix A.4 we discuss the performance of the strategy for these two additional models of volatility.

# Appendix A.3. Parameter estimates and sensitivity analysis

Recall that we estimate daily parameters of the model for volatility during the period from December 2016 to March 2017, i.e., 83 trading days. In total, we employ around 170,000 observations of the micro-exchange rate because we sample prices every 500 milliseconds, and around 2,800 observations for the fill ratio because we sample fills and misses every 30 seconds. In our analysis, the OLS regressions are not restricted to obtain non-negative parameter estimates. In Tables A.11 and A.12 we report the number of occurrences when a parameter estimate is negative. In these few cases, to run the strategy, we replace the set of parameters with those of the previous day.

| Volatility model                                    | (6): $\hat{\kappa}, \hat{\bar{v}}, \hat{\sigma_v}$ | (7): $\hat{\kappa}^a, \hat{\bar{v}}^a, \hat{\sigma_v}^a$ | (8): $\hat{\kappa}^b, \hat{\bar{v}}^b, \hat{\sigma_v}^b$ |
|-----------------------------------------------------|----------------------------------------------------|----------------------------------------------------------|----------------------------------------------------------|
| Days with at least one estimated negative parameter | 1                                                  | 7                                                        | 7                                                        |

<span id="page-31-2"></span>Table A.11: Number of days with at least one negative parameter estimate (out of 83 days).

Table A.12 shows the number of days in which the parameter estimates of the dynamics of fill ratio dynamics are negative.

<span id="page-32-1"></span>

|                                                     | $\hat{a}$ | $\hat{b}$ | $\hat{\lambda}$ | $\hat{\bar{F}}$ | $\hat{\sigma}_F$ |
|-----------------------------------------------------|-----------|-----------|-----------------|-----------------|------------------|
| Days with at least one estimated negative parameter | 1         | 12        | 1               | 1               | 1                |

Table A.12: Number of days with at least one negative parameter estimate (out of 83 days)

#### <span id="page-32-0"></span>Appendix A.3.1. Sensitivity to parameter estimates

In Tables A.13 and A.14 we show the performance of the optimal strategy  $\delta^*$  when we stress the parameter estimates of the volatility model (6). For each day, we estimate the parameters  $\hat{\kappa}$ ,  $\hat{v}$ , and  $\hat{\sigma_v}$  as described in Section 5 and analyze eight scenarios, where we shock each parameter by multiplying it by 1.2 and 0.80, See subsection 6.3. Next, we compute the optimal strategy  $\delta^*$  with the eight triplets of parameters resulting from all the different combinations of  $(\hat{\kappa}, \hat{v}, \hat{\sigma_v}) \in \{\hat{\kappa}^d, \hat{\kappa}^u\} \times \{\hat{v}^d, \hat{v}^u\} \times \{\hat{\sigma}_v^d, \hat{\sigma}_v^u\}$ .

Tables A.13 and A.14 are the analogue of Tables 3 and 4.

<span id="page-32-2"></span>

|       |                                                           |                |                                  |                 | - ·                              |                                 |
|-------|-----------------------------------------------------------|----------------|----------------------------------|-----------------|----------------------------------|---------------------------------|
|       |                                                           | Extra<br>Fills | Extra<br>Volume ×10 <sup>6</sup> | Cost<br>in JPY  | Cost<br>20ms later<br>in JPY     | Cost<br>100ms later<br>in JPY   |
| (a)   | $\delta_t = \infty ,  \forall t$                          | 9,483          | 4,222                            | 8,914,046       | 9,841,755                        | 12,158,945                      |
|       | $\delta^*, \ \hat{\delta} = 0$                            |                |                                  |                 | $\delta_t = \infty ,  \forall t$ | $\delta_t = \infty , \forall t$ |
|       | Parameters                                                |                |                                  |                 |                                  |                                 |
| (b)   | $\hat{\kappa},\hat{\bar{v}},\hat{\sigma_v}$               | 8,318          | 3,718                            | $6,\!528,\!965$ | 7,459,198                        | 9,601,222                       |
| (b.1) | $\hat{\kappa}^d$ , $\hat{\bar{v}}^d$ , $\hat{\sigma_v}^d$ | 8,434          | 3,765                            | 6,633,578       | 7,579,730                        | 9,741,145                       |
| (b.2) | $\hat{\kappa}^d$ , $\hat{\bar{v}}^d$ , $\hat{\sigma_v}^d$ | 8,434          | 3,765                            | 6,633,578       | 7,579,730                        | 9,741,145                       |
| (b.3) | $\hat{\kappa}^d$ , $\hat{\bar{v}}^u$ , $\hat{\sigma_v}^d$ | 8,225          | 3,688                            | 6,507,051       | 7,421,755                        | 9,541,736                       |
| (b.4) | $\hat{\kappa}^d$ , $\hat{\bar{v}}^u$ , $\hat{\sigma_v}^d$ | 8,225          | 3,688                            | 6,507,051       | 7,421,755                        | 9,541,736                       |
| (b.5) | $\hat{\kappa}^u$ , $\hat{\bar{v}}^d$ , $\hat{\sigma_v}^d$ | 8,041          | 3,757                            | 6,621,327       | 7,563,658                        | 9,722,004                       |
| (b.6) | $\hat{\kappa}^u$ , $\hat{\bar{v}}^d$ , $\hat{\sigma_v}^d$ | 8,041          | 3,757                            | 6,621,327       | 7,563,658                        | 9,722,004                       |
| (b.7) | $\hat{\kappa}^u$ , $\hat{\bar{v}}^u$ , $\hat{\sigma_v}^d$ | 7,839          | 3,683                            | 6,494,442       | 7,408,846                        | 9,527,502                       |
| (b.8) | $\hat{\kappa}^u$ , $\hat{\bar{v}}^u$ , $\hat{\sigma_v}^d$ | 7,839          | 3,683                            | 6,494,442       | 7,408,846                        | 9,527,502                       |

Table A.13: Sensitivity analysis (volatility parameters) of the performance of optimal strategy for T1. The total number of trade attempts is 110,458. Cost-related quantities are in JPY. Parameters:  $\phi_{\delta} = 5 \times 10^{-5}$ ,  $\phi_{F} = 5$ ,  $\varphi = 10^{-3}$ ,  $\hat{F} = 100\%$ , and T = 5 days. Period is from 5 December 2016 to 31 March 2017, currency pair USD/JPY.

<span id="page-33-1"></span>

|       |                                                           |                | Missed by naive, filled by alternative strategies |                                     |                                      |                                                                                |                                                                                 |  |
|-------|-----------------------------------------------------------|----------------|---------------------------------------------------|-------------------------------------|--------------------------------------|--------------------------------------------------------------------------------|---------------------------------------------------------------------------------|--|
|       |                                                           | Extra<br>Fills | Avg.<br>cost<br>in ticks                          | Avg. cost<br>20ms later<br>in ticks | Avg. cost<br>100ms later<br>in ticks | $\begin{array}{c} \text{Cost increase} \\ \text{20ms later} \\ \% \end{array}$ | $\begin{array}{c} \text{Cost increase} \\ \text{100ms later} \\ \% \end{array}$ |  |
| (a)   | $\delta_t = \infty , \forall t$                           | 9,483          | 2.11                                              | 2.33                                | 2.88                                 | 10%                                                                            | 36%                                                                             |  |
|       | $\delta^*,  \hat{\delta} = 0$                             |                |                                                   |                                     |                                      | $\delta_t = \infty ,  \forall t$                                               | $\delta_t = \infty ,  \forall t$                                                |  |
|       | Parameters                                                |                |                                                   |                                     |                                      |                                                                                |                                                                                 |  |
| (b)   | $\hat{\kappa},\hat{\bar{v}},\hat{\sigma_v}$               | 8,318          | 1.76                                              | 2.01                                | 2.58                                 | 14%                                                                            | 47%                                                                             |  |
| (b.1) | $\hat{\kappa}^d,\hat{\bar{v}}^d,\hat{\sigma_v}^d$         | 8,434          | 1.76                                              | 2.01                                | 2.59                                 | 14%                                                                            | 47%                                                                             |  |
| (b.2) | $\hat{\kappa}^d$ , $\hat{\bar{v}}^d$ , $\hat{\sigma_v}^d$ | 8,434          | 1.76                                              | 2.01                                | 2.59                                 | 14%                                                                            | 47%                                                                             |  |
| (b.3) | $\hat{\kappa}^d$ , $\hat{\bar{v}}^u$ , $\hat{\sigma_v}^d$ | 8,225          | 1.76                                              | 2.01                                | 2.59                                 | 14%                                                                            | 47%                                                                             |  |
| (b.4) | $\hat{\kappa}^d$ , $\hat{\bar{v}}^u$ , $\hat{\sigma_v}^d$ | 8,225          | 1.76                                              | 2.01                                | 2.59                                 | 14%                                                                            | 47%                                                                             |  |
| (b.5) | $\hat{\kappa}^u$ , $\hat{\bar{v}}^d$ , $\hat{\sigma_v}^d$ | 8,041          | 1.76                                              | 2.01                                | 2.59                                 | 14%                                                                            | 47%                                                                             |  |
| (b.6) | $\hat{\kappa}^u,\hat{\bar{v}}^d,\hat{\sigma_v}^d$         | 8,041          | 1.76                                              | 2.01                                | 2.59                                 | 14%                                                                            | 47%                                                                             |  |
| (b.7) | $\hat{\kappa}^u$ , $\hat{\bar{v}}^u$ , $\hat{\sigma_v}^d$ | 7,839          | 1.76                                              | 2.01                                | 2.59                                 | 14%                                                                            | 47%                                                                             |  |
| (b.8) | $\hat{\kappa}^u, \hat{\bar{v}}^u, \hat{\sigma_v}^d$       | 7,839          | 1.76                                              | 2.01                                | 2.59                                 | 14%                                                                            | 47%                                                                             |  |

Table A.14: Sensitivity analysis (of volatility parameter) of the performance of optimal strategy for T1. The total number of trade attempts is 110,458. Cost-related quantities are weighted by volume and expressed in ticks,  $10^{-3}$  JPY. The metrics in column 6 (resp. 7) are the proportional increase of the values in columns 5 and 6 (resp. 5 and 7) in Table 3. Parameters:  $\phi_{\delta} = 5 \times 10^{-5}$ ,  $\phi_{F} = 5$ ,  $\varphi = 10^{-3}$ ,  $\hat{F} = 100\%$ , and T = 5 days. Period is from 5 December 2016 to 31 March 2017, currency pair USD/JPY.

# <span id="page-33-0"></span>Appendix A.4. Performance of the Optimal Strategy for Alternative Models of Volatility

Table A.15 presents the performance of the optimal strategy for three volatility models of the micro-exchange rate. We observe small differences with respect to the baseline model in row (b). Finally, Table A.16 summarizes the results of Table A.15 using average figures.

<span id="page-33-2"></span>

|     |                                 | Missed by naive, filled by alternative strategies |                                  |                 |                                |                                |  |  |  |
|-----|---------------------------------|---------------------------------------------------|----------------------------------|-----------------|--------------------------------|--------------------------------|--|--|--|
|     |                                 | Extra<br>Fills                                    | Extra<br>Volume ×10 <sup>6</sup> | Cost in JPY     | Cost<br>20ms later<br>in JPY   | Cost<br>100ms later<br>in JPY  |  |  |  |
| (a) | $\delta_t = \infty , \forall t$ | 9,483                                             | 4,222                            | 8,914,046       | 9,841,755                      | 12,158,945                     |  |  |  |
|     | $\delta^*, \ \hat{\delta} = 0$  |                                                   |                                  |                 | $\delta_t = \infty, \forall t$ | $\delta_t = \infty, \forall t$ |  |  |  |
|     | Volatility model                |                                                   |                                  |                 |                                |                                |  |  |  |
| (b) | Equation (6)                    | 8,318                                             | 3,718                            | $6,\!528,\!965$ | $7,\!459,\!198$                | 9,601,222                      |  |  |  |
| (c) | Equation (7)                    | 8,434                                             | 3,792                            | 6,711,593       | 7,663,781                      | 9,868,183                      |  |  |  |
| (d) | Equation (8)                    | 8,434                                             | 3,713                            | 6,529,054       | 7,465,914                      | 9,593,287                      |  |  |  |

Table A.15: Performance of optimal strategy for T1 for three volatility models of the micro-exchange rate. The total number of trade attempts is 110,458. Cost-related quantities are in JPY. Parameters:  $\phi_{\delta} = 5 \times 10^{-5}$ ,  $\phi_F = 5$ ,  $\varphi = 10^{-3}$ ,  $\hat{F} = 100\%$ , and T = 5 days. Period is from 5 December 2016 to 31 March 2017, currency pair USD/JPY.

<span id="page-34-2"></span>

|     |                                          | Missed by naive, filled by alternative strategies |                          |                                     |                                      |                                                                                |                                            |  |  |  |
|-----|------------------------------------------|---------------------------------------------------|--------------------------|-------------------------------------|--------------------------------------|--------------------------------------------------------------------------------|--------------------------------------------|--|--|--|
|     |                                          | Extra<br>Fills                                    | Avg.<br>cost<br>in ticks | Avg. cost<br>20ms later<br>in ticks | Avg. cost<br>100ms later<br>in ticks | $\begin{array}{c} \text{Cost increase} \\ \text{20ms later} \\ \% \end{array}$ | Cost increase $100 \mathrm{ms}$ later $\%$ |  |  |  |
| (a) | $\delta_t = \infty , \forall t$          | 9,483                                             | 2.11                     | 2.33                                | 2.88                                 | 10%                                                                            | 36%                                        |  |  |  |
|     | $\delta^*,  \hat{\delta} = 0$ Parameters |                                                   |                          |                                     |                                      | $\delta_t = \infty , \forall t$                                                | $\delta_t = \infty ,  \forall t$           |  |  |  |
| (b) | Equation (6)                             | 8,318                                             | 1.76                     | 2.01                                | 2.58                                 | 14%                                                                            | 47%                                        |  |  |  |
| (c) | Equation (7)                             | 8,395                                             | 1.77                     | 2.02                                | 2.60                                 | 14%                                                                            | 47%                                        |  |  |  |
| (d) | Equation (8)                             | 8,307                                             | 1.76                     | 2.01                                | 2.58                                 | 14%                                                                            | 47%                                        |  |  |  |

Table A.16: Performance of optimal strategy for T1 under different models for the volatility of the micro-exchange rate. The total number of trade attempts is 110,458. Cost-related quantities are weighted by volume and expressed in ticks,  $10^{-3}$  JPY. The metrics in column 6 (resp. 7) are the proportional increase of the values in columns 5 and 6 (resp. 5 and 7) in Table 3. Parameters:  $\phi_{\delta} = 5 \times 10^{-5}$ ,  $\phi_{F} = 5$ ,  $\varphi = 10^{-3}$ ,  $\hat{F} = 100\%$ , and T = 5 days. Period is from 5 December 2016 to 31 March 2017, currency pair USD/JPY.

### <span id="page-34-0"></span>Appendix A.5. Infinite-horizon value function

We solve the infinite-horizon problem for the trader, which is the analogue to (13) with  $T \to \infty$  and here we include an exponential discount factor  $\beta > 0$ , so the problem is well defined. Thus, the trader's value function is

$$H(f, v) = \sup_{\delta \in \mathcal{A}_{0,\infty}} \inf_{\mathbb{Q} \in \mathbf{Q}} \mathbb{E}_{f,v}^{\mathbb{Q}} \left[ - \int_{0}^{\infty} e^{-\beta s} \left( \phi_{\delta} \left( \delta_{s} - \hat{\delta} \right)^{2} ds + \phi_{F} \left( F_{s}^{\delta} - \hat{F} \right)^{2} \right) ds + \mathcal{H}^{\beta} \left( \mathbb{Q} \mid \mathbb{P} \right) \right], \quad (A.9)$$

where we now define the penalty as

<span id="page-34-1"></span>
$$\mathcal{H}^{\beta}\left(\mathbb{Q}\,|\,\mathbb{P}\right) = \frac{1}{\varphi}\,\log\left(\exp\left(-\frac{1}{2}\,\int_{0}^{\infty}e^{-\beta\,s}\,\left(x_{s}^{F}\right)^{2}\mathrm{d}s - \int_{0}^{\infty}e^{-\beta\,s}\,x_{s}^{F}\mathrm{d}W_{s}^{F}\right)\right).$$

As above, the value function satisfies the HJBI

$$-\beta H + \sup_{\delta} \inf_{x} \left( \left( \lambda \left( \bar{F} - f \right) + a \, \delta - b \left( v - \bar{v} \right) - \sigma_{F} \, x \right) H_{f} + \frac{1}{2} \, \sigma_{F}^{2} \, H_{ff} + \frac{1}{2 \, \varphi} \, x^{2} \right.$$

$$\left. + \kappa \left( \bar{v} - v \right) H_{v} + \frac{1}{2} \, v^{2} \, \sigma_{v}^{2} \, H_{vv} - \phi_{\delta} \, \left( \delta - \hat{\delta} \right)^{2} - \phi_{F} \, \left( f - \hat{F} \right)^{2} \right) = 0 \,, \tag{A.10}$$

which, after substituting the feedback controls, reduces to

$$\begin{split} -\beta \, H + \left( \lambda \left( \bar{F} - f \right) - b \left( v - \bar{v} \right) \right) \, H_f + \frac{1}{2} \, \sigma_F^2 \, H_{ff} + \frac{a^2 \, V_f^2}{2 \, \phi_\delta} - \frac{1}{2} \, \varphi \, H_f^2 \, \sigma_F^2 + a \, \hat{\delta} \, H_f \\ + \kappa \left( \bar{v} - v \right) H_v + \frac{1}{2} \, v^2 \, \sigma_v^2 \, H_{vv} - \phi_F \, \left( f - \hat{F} \right)^2 = 0 \, . \end{split}$$

We use a similar ansatz to that in (19)

$$H(f, v) = k_0 + k_1 f + k_2 f^2 + k_3 v + k_4 v^2 + k_5 f v,$$
(A.11)

where  $k_0$ ,  $k_1$ ,  $k_2$ ,  $k_3$ ,  $k_4$ ,  $k_5$  are constants. Substitute the ansatz in the HJBI and collect terms to obtain the system of equations:

$$-\beta k_{0} + (b \bar{v} + a \hat{\delta} + \lambda \bar{F}) k_{1} + \sigma_{F}^{2} k_{2} + \kappa \bar{v} k_{3} + \frac{1}{2} \left( \frac{a^{2}}{\phi_{\delta}} - \varphi \sigma_{F}^{2} \right) (k_{1})^{2} - \phi_{F} \hat{F}^{2} = 0,$$

$$-\beta k_{1} + (2 b \bar{v} + 2 \lambda \bar{F} + 2 a \hat{\delta}) k_{2} - \lambda k_{1} + \kappa \bar{v} k_{5} + 2 \left( \frac{a^{2}}{\phi_{\delta}} - \varphi \sigma_{F}^{2} \right) k_{1} k_{2} + 2 \phi_{F} \hat{F} = 0,$$

$$-\beta k_{2} - 2 \lambda k_{2} + 2 \left( \frac{a^{2}}{\phi_{\delta}} - \varphi \sigma_{F}^{2} \right) (k_{2})^{2} - \phi_{F} = 0,$$

$$-\beta k_{3} - b k_{1} + (b \bar{v} + a \hat{\delta} + \lambda \bar{F}) k_{5} + 2 \kappa \bar{v} k_{4} - \kappa k_{3} + \left( \frac{a^{2}}{\phi_{\delta}} - \varphi \sigma_{F}^{2} \right) k_{1} k_{5} = 0,$$

$$-\beta k_{4} - b k_{5} + (\sigma_{v}^{2} - 2 \kappa) k_{4} + \frac{1}{2} \left( \frac{a^{2}}{\phi_{\delta}} - \varphi \sigma_{F}^{2} \right) (k_{5})^{2} = 0,$$

$$-\beta k_{5} - 2 b k_{2} - (\lambda + \kappa) k_{5} + 2 \left( \frac{a^{2}}{\phi_{\delta}} - \varphi \sigma_{F}^{2} \right) k_{2} k_{5} = 0.$$

In Tables A.17 and A.18, which are the analogues of Tables 3 and 4, we compare the performance of the strategy in the finite- and infinite-horizon cases. The results are broadly the same – recall that in the finite-horizon case we assume that every day the latency-optimal strategy assumes T = 5.

<span id="page-35-0"></span>

|     |                                              | ľ              | Missed by naive, filled by alternative strategies |                |                                  |                                 |  |  |  |  |
|-----|----------------------------------------------|----------------|---------------------------------------------------|----------------|----------------------------------|---------------------------------|--|--|--|--|
|     |                                              | Extra<br>Fills | Extra<br>Volume ×10 <sup>6</sup>                  | Cost<br>in JPY | Cost<br>20ms later<br>in JPY     | Cost<br>100ms later<br>in JPY   |  |  |  |  |
| (a) | $\delta_t = \infty , \forall t$              | 9,483          | 4,222                                             | 8,914,046      | 9,841,755                        | 12,158,945                      |  |  |  |  |
|     | $\delta^*,  \hat{\delta} = 0$ Value function |                |                                                   |                | $\delta_t = \infty ,  \forall t$ | $\delta_t = \infty , \forall t$ |  |  |  |  |
| (b) | Finite-horizon                               | 8,318          | 3,718                                             | 6,528,965      | 7,459,198                        | 9,601,222                       |  |  |  |  |
| (c) | Infinite-horizon                             | 8,317          | 3,718                                             | 6,527,965      | 7,458,198                        | 9,600,222                       |  |  |  |  |

Table A.17: Performance of optimal strategy for T1 for finite and infinite horizon cases. The total number of trade attempts is 110,458. Cost-related quantities are in JPY. Parameters:  $\phi_{\delta} = 5 \times 10^{-5}$ ,  $\phi_{F} = 5$ ,  $\varphi = 10^{-3}$ ,  $\hat{F} = 100\%$ ,  $\beta = 0.01$ , and T = 5 days in the finite-horizon case. Period is from 5 December 2016 to 31 March 2017, currency pair USD/JPY.

<span id="page-36-0"></span>

|     |                                               |                | S                        |                                     |                                      |                                                                                |                                 |
|-----|-----------------------------------------------|----------------|--------------------------|-------------------------------------|--------------------------------------|--------------------------------------------------------------------------------|---------------------------------|
|     |                                               | Extra<br>Fills | Avg.<br>cost<br>in ticks | Avg. cost<br>20ms later<br>in ticks | Avg. cost<br>100ms later<br>in ticks | $\begin{array}{c} \text{Cost increase} \\ \text{20ms later} \\ \% \end{array}$ | Cost increase 100ms later $\%$  |
| (a) | $\delta_t = \infty , \forall t$               | 9,483          | 2.11                     | 2.33                                | 2.88                                 | 10%                                                                            | 36%                             |
|     | $\delta^*, \ \hat{\delta} = 0$ Value function |                |                          |                                     |                                      | $\delta_t = \infty , \forall t$                                                | $\delta_t = \infty , \forall t$ |
| (b) | Finite-horizon                                | 8,318          | 1.76                     | 2.01                                | 2.58                                 | 14%                                                                            | 47%                             |
| (c) | Infinite-horizon                              | 8,317          | 1.76                     | 2.01                                | 2.58                                 | 14%                                                                            | 47%                             |

Table A.18: Performance of optimal strategy for T1 for finite and infinite horizon cases. The total number of trade attempts is 110,458. Cost-related quantities are weighted by volume and expressed in ticks,  $10^{-3}$  JPY. The metrics in column 6 (resp. 7) are the proportional increase of the values in columns 5 and 6 (resp. 5 and 7) in Table 3. Parameters:  $\phi_{\delta} = 5 \times 10^{-5}$ ,  $\phi_{F} = 5$ ,  $\varphi = 10^{-3}$ ,  $\hat{F} = 100\%$ ,  $\beta = 0.01$ , and T = 5 days in the finite-horizon case. Period is from 5 December 2016 to 31 March 2017, currency pair USD/JPY.

# Appendix A.6. Proof of Theorem 1.

Here we provide a class of controls that produces strong solutions for  $F^{\delta}$  and v, see Lemma 1. We employ Lemma 1 to prove the admissibility of the control  $\delta^*$  (see Corollary 1). Then we prove that the control  $x^*$  is also admissible and conclude this section with the verification of the value function.

<span id="page-36-1"></span>**Lemma 1.** Let  $\delta_t = \mu(t, F_t, v_t)$  with  $\mu \in \mathcal{M}_{0,T}$ . Then, for all  $t \in [0, T]$  there exist strong solutions to the SDEs of  $F^{\delta}$  and v.

*Proof.* Let  $\delta_t = \mu(t, F_t, v_t)$ , for  $\mu \in \mathcal{M}_{0,T}$ . Thus, there exists  $K \in \mathbb{R}$  such that for all  $t \in [0, T]$ ,  $x, y \in \mathbb{R}^2$ 

$$|\mu(t, x) - \mu(t, y)| \le K |x - y|, \text{ and } |\mu(t, x)|^2 \le K^2 (1 + |x|^2).$$
 (A.12)

Let  $\boldsymbol{Z}_t^{\delta} = (F_t^{\delta}, v_t)^{\mathsf{T}}$ , thus

$$d\mathbf{Z}_{t}^{\delta} = (A(t) + B(t) \mathbf{Z}_{t}^{\delta} + \boldsymbol{\mu}(t, \mathbf{Z}_{t}^{\delta})) dt + C_{t} d\mathbf{W}_{t},$$

with A(t), B(t),  $C_t$ , and  $\mu$  given by

$$A(t) = \begin{bmatrix} \lambda \, \bar{F} + b \, \bar{v} \\ \kappa \, \bar{v} \end{bmatrix}, \quad B(t) = \begin{bmatrix} -\lambda & -b \\ 0 & -\kappa \end{bmatrix}, \quad C_t = \begin{bmatrix} \sigma_F & 0 \\ 0 & \sigma_v \, v_t \end{bmatrix}, \quad \boldsymbol{\mu}(t, \boldsymbol{Z}_t^{\delta}) = \begin{bmatrix} a \, \mu(t, \boldsymbol{Z}_t^{\delta}) \\ 0 \end{bmatrix}.$$

Define the functions  $c:[0,T]\times\mathbb{R}^2\to\mathbb{R}^2$ , and  $\sigma:[0,T]\times\mathbb{R}^2\to\mathbb{R}^{2\times 2}$ , which are given by

$$c(t, \mathbf{Z}) = (A(t) + B(t) \mathbf{Z} + \mu(t, \mathbf{Z})),$$
  $\sigma(t, \mathbf{Z}) = \begin{bmatrix} \sigma_F & 0 \\ 0 & \sigma_v v_t \end{bmatrix}.$ 

Now, let  $t \in [0,T]$ ,  $\mathbf{Z_1}$ ,  $\mathbf{Z_2} \in \mathbb{R}^2$ . We first verify the Lipschitz condition on the function c,

$$|c(t, \mathbf{Z_1}) - c(t, \mathbf{Z_2})| = |B(t) (\mathbf{Z_1} - \mathbf{Z_2}) + \mu(t, \mathbf{Z_1}) - \mu(t, \mathbf{Z_2})|$$

$$\leq |B(t)| |\mathbf{Z_1} - \mathbf{Z_2}| + |\mu(t, \mathbf{Z_1}) - \mu(t, \mathbf{Z_2})|$$

$$\leq \bar{B} |\mathbf{Z_1} - \mathbf{Z_2}| + K |\mathbf{Z_1} - \mathbf{Z_2}| = \hat{K} |\mathbf{Z_1} - \mathbf{Z_2}|,$$

for  $\hat{K} = K + \bar{B}$ , and  $\bar{B} = \max_{t \in [0,T]} B(t)$ , which is clearly attained. For the function  $\sigma$ , we have

$$|\sigma(t, \mathbf{Z_1}) - \sigma(t, \mathbf{Z_2})| \leq \sigma_v |\mathbf{Z_1} - \mathbf{Z_2}|$$

We test the linear growth condition on the function c. We use triangle inequalities and simple bounds to obtain

$$|c(t, \mathbf{Z_{1}})|^{2} = |A(t) + B(t) \mathbf{Z_{1}} + \mu(t, \mathbf{Z_{1}})|^{2} \le (|A(t)| + |B(t) \mathbf{Z_{1}}| + |\mu(t, \mathbf{Z_{1}})|)^{2}$$

$$\le 3 |A(t)|^{2} + 3 |B(t)|^{2} |\mathbf{Z_{1}}|^{2} + 3 |\mu(t, \mathbf{Z_{1}})|^{2}$$

$$\le 3 \overline{A}^{2} + 3 \overline{B}^{2} |\mathbf{Z_{1}}|^{2} + 3 K^{2} (1 + |\mathbf{Z_{1}}|^{2})$$

$$\le \overline{D}^{2} + \overline{D}^{2} |\mathbf{Z_{1}}|^{2} + 3 K^{2} (1 + |\mathbf{Z_{1}}|^{2})$$

$$= (\overline{D}^{2} + 3 K^{2}) (1 + |\mathbf{Z_{1}}|^{2}),$$

for  $\bar{A} = \max_{t \in [0,T]} A(t)$ , which is clearly attained. Finally, we take  $\bar{D}^2 = \max\{\bar{A}^2, \bar{B}^2\}$ . On the other hand, for  $\sigma$ , we have

$$|\sigma(t, \mathbf{Z}_1)|^2 \le 2\sigma_F^2 + 2\sigma_v^2 |\mathbf{Z}_1|^2$$
  
$$\le \bar{E}^2 \left(1 + |\mathbf{Z}_1|^2\right),$$

for  $\bar{E} = \max{\{\sigma_F^2, \sigma_v^2\}}$ . Lipschitz and linear growth conditions follow by choosing

$$\bar{K} = \max \left\{ \bar{E}, \sqrt{\bar{D}^2 + 3K^2}, \, \sigma_v \,, \hat{K} \right\} < \infty \,.$$

Thus the Lipschitz and linear growth conditions are satisfied, therefore, for all  $t \in [0, T]$ , there exits a strong solution to the SDE satisfied by  $\mathbf{Z}^{\delta}$ , and subsequently  $F^{\delta}$  and  $v_t$ .

<span id="page-37-0"></span>Corollary 1. Let  $\delta \in \mathcal{A}_{t,T}$ . Then, for all  $t \in [0, T]$  there exist strong solutions to the SDEs of  $F^{\delta}$  and v.

This shows that as long as the control  $\delta$  is admissible,  $F^{\delta}$  and v have strong solutions.

*Proof.* Let  $\delta \in \mathcal{A}_{t,T}$ , thus there exist  $\mu \in \mathcal{M}_{0,T}$  such that  $\delta_t = \mu(t, F_t, v_t)$ . By Lemma 1, for all  $t \in [0, T]$  there exist strong solutions to the SDEs of  $F^{\delta}$  and v.

*Proof.* The control  $\delta^*$  is admissible.

Recall that  $\delta^*$  is given by

$$\delta_t^* = \hat{\delta} + \frac{a}{2 \phi_{\delta}} \left( h_1(t) + 2 h_2(t) F_t^{\delta^*} + h_5(t) v_t \right).$$

Define  $f:[0,T]\times\mathbb{R}\times\mathbb{R}\mapsto\mathbb{R}$  as

$$f(t,x,y) = \hat{\delta} + \frac{a}{2\phi_{\delta}}h_1(t) + \frac{ah_2(t)}{\phi_{\delta}}x + \frac{ah_5(t)}{2\phi_{\delta}}y,$$

so  $\delta_t^* = f(t, F_t, v_t)$ , and, since f is linear in x and y, and a continuous function of t, then  $f \in \mathcal{M}_{0,T}$ . The control  $\delta^*$  is  $\mathcal{F}$ -adapted, because it is a continuous function of two  $\mathcal{F}$ -adapted processes. Then, we only need to prove that

$$\mathbb{E}\left[\int_0^T \left(\delta_s^*\right)^2 \mathrm{d}s\right] < \infty.$$

Based on Young's inequality we find the following bound for the optimal control:

$$\left(\delta_t^*\right)^2 \leq 2\left(\hat{\delta} + \frac{a}{2\phi_{\delta}}h_1(t)\right)^2 + \frac{2a^2}{\phi_{\delta}^2}\left(h_2(t)\right)^2\left(F_t^{\delta^*}\right)^2 + \frac{a^2}{2\phi_{\delta}^2}\left(h_5(t)\right)^2\left(v_t\right)^2,$$

and because  $h_1$ ,  $h_2$  and  $h_5$  are continuous functions in the closed interval [0, T], they are bounded. Let U be an upper bound for  $|h_1|$ ,  $|h_2|$ , and  $|h_5|$  on [0, T].

As  $\delta_t^* = f(t, F_t, v_t)$  for  $f \in \mathcal{M}_{0,T}$ , by Lemma 1, we have that  $F^{\delta^*}$  and v have strong solutions for all  $t \in [0, T]$ , thus

<span id="page-38-0"></span>
$$\mathbb{E}\left[\sup_{0 \le t \le T} \left(F_t^{\delta^*}\right)^2\right] < \infty \quad \text{and} \quad \mathbb{E}\left[\sup_{0 \le t \le T} \left(v_t\right)^2\right] < \infty. \tag{A.13}$$

Finally, using the upper bound U and the inequalities in (A.13), we conclude that

$$\mathbb{E}\left[\int_{0}^{T} \left(\delta_{s}^{*}\right)^{2} ds\right] \leq \mathbb{E}\left[\int_{0}^{T} 2\left(\hat{\delta} + \frac{a}{2\phi_{\delta}}h_{1}(t)\right)^{2} + \frac{2a^{2}}{\phi_{\delta}^{2}}\left(h_{2}(t)\right)^{2}\left(F_{t}^{\delta^{*}}\right)^{2} + \frac{a^{2}}{2\phi_{\delta}^{2}}\left(h_{5}(t)\right)^{2}\left(v_{t}\right)^{2}\right]$$

$$\leq \mathbb{E}\left[2T\left(\hat{\delta} + \frac{a}{2\phi_{\delta}}U\right)^{2} + \frac{2a^{2}}{\phi_{\delta}^{2}}U^{2}\sup_{0\leq t\leq T}\left(F_{t}^{\delta^{*}}\right)^{2} + T\frac{a^{2}}{2\phi_{\delta}^{2}}U^{2}\sup_{0\leq t\leq T}\left(v_{t}\right)^{2}\right]$$

$$\leq \infty$$

#### *Proof.* The control $x^*$ is admissible.

This proof is similar to that of Theorem 1 in Cheridito et al. (2007).

Let  $\delta \in \mathcal{A}_{t,T}$ , then  $\exists \mu \in \mathcal{M}_{t,T}$ , such that  $\delta_t = \mu(t, F_t, v_t)$ . Recall that the optimal control  $x^*$  is given by

$$x_t^* = \varphi \, \sigma_F \left( h_1(t) + 2 \, h_2(t) \, F_t^{\delta} + h_5(t) \, v_t \right)$$
$$= \eta(t, F_t, v_t) \,,$$

which is adapted because it is a continuous function of adapted processes. Therefore, it remains to show that

$$Z_t = \exp\left\{-\frac{1}{2} \int_0^t (x_u^*)^2 du - \int_0^t x_u^* dW_u^F\right\},$$

is a martingale. As the control  $x^*$  is a well-defined continuous process, Z is a well-defined local martingale with respect to  $\mathbb{P}$ , and subsequently, because Z is non-negative, it follows that it is a super-martingale, and for it to be a martingale, we only need to prove that

$$\mathbb{E}^{\mathbb{P}}\left[Z_{T}\right]$$
 = 1.

Consider the function  $\mu^{\mathbb{Q}}$  given by

$$\mu^{\mathbb{Q}}(t, F_t, v_t) = \mu(t, F_t, v_t) - \frac{\sigma_F}{a} \eta(t, F_t, v_t),$$

and because the term  $\eta(t, F_t, v_t)$  is continuous in time and linear in F and v, it belongs to  $\mathcal{M}_{t,T}$ , therefore  $\mu^{\mathbb{Q}} \in \mathcal{M}_{t,T}$ .

Given that  $\mu$ ,  $\mu^{\mathbb{Q}} \in \mathcal{M}_{t,T}$ , by Lemma 1, we know there is a strong solution for the SDEs given by

$$dF_t = \left(\lambda \left(\bar{F} - F_t\right) + a\,\mu(t, F_t, v_t) - b\left(v_t - \bar{v}\right)\right)\,dt + \sigma_F\,dW_t^F\,,\tag{A.14}$$

$$d\tilde{F}_t = \left(\lambda \left(\bar{F} - \tilde{F}_t\right) + a\,\mu^{\mathbb{Q}}(t, \tilde{F}_t, v_t) - b\left(v_t - \bar{v}\right)\right) dt + \sigma_F dW_t^F. \tag{A.15}$$

Now define

$$\tilde{x}_t^* = \varphi \,\sigma_F \left( h_1(t) + 2 \,h_2(t) \,\tilde{F}_t^{\delta} + h_5(t) \,v_t \right) \tag{A.16}$$

$$= \eta(t, \tilde{F}_t, v_t). \tag{A.17}$$

For  $n \in \mathbb{N}$ , consider the stopping times  $\tau_n$ , and  $\tilde{\tau}_n$ 

<span id="page-39-0"></span>
$$\tau_n = \inf \{t > 0 \mid x_t^* \ge n\} \land T \qquad \text{and} \qquad \tilde{\tau}_n = \inf \{t > 0 \mid \tilde{x}_t^* \ge n\} \land T, \tag{A.18}$$

and because  $x^*$  and  $\tilde{x}^*$  are  $\mathbb{P}$ -a.s. finite, then

$$\lim_{n \to \infty} \mathbb{P}(\tau_n = T) = \lim_{n \to \infty} \mathbb{P}(\tilde{\tau}_n = T) = 1. \tag{A.19}$$

Define for each  $n \in \mathbb{N}$  the process

$$x_t^{(n)} = x_t^* \mathbf{1}_{\{t \le \tau_n\}},$$

which satisfies the Novikov's condition

$$\mathbb{E}^{\mathbb{P}}\left[\exp\left\{\frac{1}{2}\int_{0}^{T}\left(x_{u}^{n}\right)^{2}du\right\}\right] \leq \exp\left\{\frac{n^{2}T}{2}\right\} < \infty.$$

Then it follows that

$$\frac{\mathrm{d}\mathbb{Q}\left(x^{(n)}\right)}{\mathrm{d}\mathbb{P}}\Big|_{t} = \exp\left\{-\frac{1}{2} \int_{0}^{t} \left(x_{u}^{(n)}\right)^{2} \mathrm{d}u - \int_{0}^{t} x_{u}^{(n)} \mathrm{d}W_{u}^{F}\right\}$$
$$= Z_{t}^{(n)},$$

defines an equivalent measure to  $\mathbb{P}$ , and by Girsanov's theorem,  $W_t^n = W_t^F + \int_0^t x_s^{(n)} ds$  is a Brownian motion under the measure  $\mathbb{Q}(x^{(n)})$ , abbreviated as  $\mathbb{Q}^n$ . Finally,

$$\mathbb{E}^{\mathbb{P}} [Z_T] = \mathbb{E}^{\mathbb{P}} \left[ \lim_{n \to \infty} Z_T \mathbf{1}_{\{\tau_n = T\}} \right]$$

$$= \mathbb{E}^{\mathbb{P}} \left[ \lim_{n \to \infty} Z_T^n \mathbf{1}_{\{\tau_n = T\}} \right]$$

$$= \lim_{n \to \infty} \mathbb{E}^{\mathbb{P}} \left[ Z_T^n \mathbf{1}_{\{\tau_n = T\}} \right]$$

$$= \lim_{n \to \infty} \mathbb{E}^{\mathbb{Q}^n} \left[ \mathbf{1}_{\{\tau_n = T\}} \right]$$

$$= \lim_{n \to \infty} \mathbb{Q}^n (\tau_n = T) ,$$

where the first two equalities hold because the control  $x^*$  is  $\mathbb{P}$ -a.s. finite, and definition (A.18). The third equality follows from the monotone convergence theorem. The fourth equality is the change of measure imposed by  $Z_T^n$ .

Finally, starting at  $F_0$ , the stopped process  $F_{t \wedge \tau_n}$  under  $\mathbb{Q}^n$  is given by

$$F_{t\wedge\tau_{n}} = F_{0} + \int_{0}^{t\wedge\tau_{n}} \left(\lambda\left(\bar{F} - F_{s}\right) + a\,\mu(s, F_{s}, v_{s}) - \sigma_{F}\,x_{s}^{(n)} - b\,(v_{s} - \bar{v})\right) \,\mathrm{d}s + \int_{0}^{t\wedge\tau_{n}} \sigma_{F}\,\mathrm{d}W_{s}^{n}$$

$$= F_{0} + \int_{0}^{t\wedge\tau_{n}} \left(\lambda\left(\bar{F} - F_{s}\right) + a\,\mu(s, F_{s}, v_{s}) - \sigma_{F}\,x_{s}^{*} - b\,(v_{s} - \bar{v})\right) \,\mathrm{d}s + \int_{0}^{t\wedge\tau_{n}} \sigma_{F}\,\mathrm{d}W_{s}^{n}$$

$$= F_{0} + \int_{0}^{t\wedge\tau_{n}} \left(\lambda\left(\bar{F} - F_{s}\right) + a\,\mu^{\mathbb{Q}}(s, F_{s}, v_{s}) - b\,(v_{s} - \bar{v})\right) \,\mathrm{d}s + \int_{0}^{t\wedge\tau_{n}} \sigma_{F}\,\mathrm{d}W_{s}^{n},$$

and similarly, the stopped process  $\tilde{F}_{t\wedge\tilde{\tau}_n}$ , under  $\mathbb{P}$  is given by

$$\tilde{F}_{t\wedge\tilde{\tau}_n} = F_0 + \int_0^{t\wedge\tilde{\tau}_n} \left(\lambda\left(\bar{F} - \tilde{F}_s\right) + a\,\mu^{\mathbb{Q}}(s,\tilde{F}_s,v_s) - b\left(v_s - \bar{v}\right)\right) \,\mathrm{d}s + \int_0^{t\wedge\tilde{\tau}_n} \sigma_F \,\mathrm{d}W_s^F.$$

Therefore  $(\tilde{F}_{t \wedge \tilde{\tau}_n})_{0 \leq t \leq T}$ , and  $(F_{t \wedge \tau_n})_{0 \leq t \leq T}$  have the same distribution under  $\mathbb{Q}^n$  and  $\mathbb{P}$  respectively, thus

$$\lim_{n\to\infty} \mathbb{Q}^n \left( \tau_n = T \right) = \lim_{n\to\infty} \mathbb{P} \left( \tilde{\tau}_n = T \right) = 1,$$

and

$$\mathbb{E}^{\mathbb{P}}\left[Z_{T}\right] = \lim_{n \to \infty} \mathbb{Q}^{n} \left(\tau_{n} = T\right) = \lim_{n \to \infty} \mathbb{P}\left(\tilde{\tau}_{n} = T\right) = 1,$$

which concludes the proof.

Finally, we present the proof of Theorem 1, i.e., we show that (19) is the trader's value function given in (13).

*Proof.* V is the value function of the trader's control problem in (13).

Let  $\mathbb{Q}^* = \mathbb{Q}^*(\delta)$  be the measure inferred by  $x_t^*(\delta) = \varphi \, \sigma_F \, (h_1(t) + 2 \, h_2(t) \, F_t^{\delta} + h_5(t) \, v_t)$ , in other words,

$$\frac{\mathrm{d}\mathbb{Q}^*}{\mathrm{d}\mathbb{P}}\Big|_{T} = \exp\left\{-\frac{1}{2} \int_0^T \boldsymbol{x}_u^{*\prime} \boldsymbol{x}_u^* \,\mathrm{d}u - \int_0^T \boldsymbol{x}_u^* \,\mathrm{d}\boldsymbol{W}_u\right\},\tag{A.20}$$

<span id="page-40-0"></span>

where  $\boldsymbol{x}_t^* = (x_t^*, 0)$ . Clearly  $x_t^*(\delta)$  represents the infimum measure of (13) for an admissible  $\delta$ . The dynamics of v under  $\mathbb{Q}^*$  do not change, but the dynamics of  $F^{\delta,\mathbb{Q}^*}$  do change. Specifically

$$dF_t^{\delta,\mathbb{Q}^*} = \left(\lambda \,\bar{F} - \left(\lambda + 2\,\varphi\,\sigma_F^2\,h_2(t)\right)\,F^{\delta,\mathbb{Q}^*} + a\,\delta_t + b\,\bar{v} - \left(b + \varphi\,\sigma_F^2\,h_5(t)\right)\,v_t - \varphi\,\sigma_F^2\,h_1(t)\right)dt + \sigma_F\,dW^{F,\mathbb{Q}^*}.$$

As  $V \in \mathcal{C}^{1,2,2}$ , apply Itô's Lemma under  $\mathbb{Q}^*$ , and consider  $\delta \in \mathcal{A}_{t,T}$ , hence

$$V(T, F_T^{\delta}, v_T) = V(t, f, v) + \int_t^T \partial_s V + \mathcal{L}^{\mathbb{Q}^*} V \, \mathrm{d}s + \int_t^T \partial_v V \, \sigma_v \, v_s \, \mathrm{d}W_s^{v \, \mathbb{Q}^*} + \int_t^T \partial_f V \, \sigma_F \, \mathrm{d}W_s^{F, \mathbb{Q}^*},$$
(A.21)

where  $W_s^{F*}$  and  $W_s^{v*}$  are standard  $\mathbb{Q}^*$ -Brownian motions. The function V is a solution of (17), and  $\delta$  is an arbitrary control, thus

$$\partial_{s}V + \mathcal{L}^{\mathbb{Q}^{*}}V \leq \phi_{\delta} \left(\delta - \hat{\delta}\right)^{2} + \phi_{F} \left(f - \hat{F}\right)^{2} - \frac{1}{2\varphi} \left(x^{*}\right)^{2}.$$

Now, take expectations on both sides of (A.21) to obtain

$$0 = \mathbb{E}_{t,f,v}^{\mathbb{Q}^*} \left[ V(T, F_T^{\delta}, v_T) \right],$$

$$= V(t, f, v) + \mathbb{E}_{t,f,v}^{\mathbb{Q}^*} \left[ \int_t^T \partial_s V + \mathcal{L}_s^{\mathbb{Q}^*} V \, \mathrm{d}s \right],$$

$$\leq V(t, f, v) + \mathbb{E}_{t,f,v}^{\mathbb{Q}^*} \left[ \phi_{\delta} \int_t^T \left( \delta_s - \hat{\delta} \right)^2 \mathrm{d}s + \phi_F \int_t^T \left( F_s^{\delta} - \hat{F} \right)^2 \mathrm{d}s - \frac{1}{2\varphi} \int_t^T \left( x_s^* \right)^2 \mathrm{d}s \right],$$

$$= V(t, f, v) + \mathbb{E}_{t,f,v}^{\mathbb{Q}^*} \left[ \phi_{\delta} \int_t^T \left( \delta_s - \hat{\delta} \right)^2 \mathrm{d}s + \phi_F \int_t^T \left( F_s^{\delta} - \hat{F} \right)^2 \mathrm{d}s - \frac{1}{2\varphi} \int_t^T \left( x_s^* \right)^2 \mathrm{d}s + \frac{1}{\varphi} \int_t^T x_s^* \mathrm{d}W_s^{\mathbb{Q}^*} \right],$$

therefore

$$\mathbb{E}_{t,f,v}^{\mathbb{Q}^*} \left[ -\phi_{\delta} \int_{t}^{T} \left( \delta_{s} - \hat{\delta} \right)^{2} \mathrm{d}s - \phi_{F} \int_{t}^{T} \left( F_{s}^{\delta} - \hat{F} \right)^{2} \mathrm{d}s + \frac{1}{2 \varphi} \int_{t}^{T} \left( x_{s}^{*} \right)^{2} \mathrm{d}s - \frac{1}{\varphi} \int_{t}^{T} x_{s}^{*} \mathrm{d}W_{s}^{\mathbb{Q}^{*}} \right] \leq V(t, f, v),$$

or alternatively,

$$\mathbb{E}_{t,f,v}^{\mathbb{Q}^*} \left[ -\phi_{\delta} \int_{t}^{T} \left( \delta_{s} - \hat{\delta} \right)^{2} ds - \phi_{F} \int_{t}^{T} \left( F_{s}^{\delta} - \hat{F} \right)^{2} ds - \frac{1}{2 \varphi} \int_{t}^{T} \left( x_{s}^{*} \right)^{2} ds - \frac{1}{\varphi} \int_{t}^{T} x_{s}^{*} dW_{s} \right] \leq V(t, f, v),$$

$$\mathbb{E}_{t,f,v}^{\mathbb{Q}^*} \left[ -\phi_{\delta} \int_{t}^{T} \left( \delta_{s} - \hat{\delta} \right)^{2} ds - \phi_{F} \int_{t}^{T} \left( F_{s}^{\delta} - \hat{F} \right)^{2} ds + \mathcal{H}_{t,T} \left( \mathbb{Q} \mid \mathbb{P} \right) \right] \leq V(t, f, v),$$

and because V(t, f, v) is a bound for any  $\delta \in \mathcal{A}_{t,T}$ , we have that

$$\sup_{\delta \in \mathcal{A}_{t,T}} \mathbb{E}_{t,f,v}^{\mathbb{Q}^*} \left[ -\phi_{\delta} \int_{t}^{T} \left( \delta_{s} - \hat{\delta} \right)^{2} ds - \phi_{F} \int_{t}^{T} \left( F_{s}^{\delta} - \hat{F} \right)^{2} ds + \mathcal{H}_{t,T} \left( \mathbb{Q}^{*} \mid \mathbb{P} \right) \right] \leq V(t,f,v)$$

$$\sup_{\delta \in \mathcal{A}_{t,T}} \inf_{\mathbb{Q} \in \mathbf{Q}} \mathbb{E}_{t,f,v}^{\mathbb{Q}} \left[ -\phi_{\delta} \int_{t}^{T} \left( \delta_{s} - \hat{\delta} \right)^{2} ds - \phi_{F} \int_{t}^{T} \left( F_{s}^{\delta} - \hat{F} \right)^{2} ds + \mathcal{H}_{t,T} \left( \mathbb{Q} \mid \mathbb{P} \right) \right] \leq V(t,f,v) , \quad (A.22)$$

which completes the first part of the proof.

Now, fix the strategy  $\delta^*$ , then for any  $\mathbb{Q} \in \mathcal{Q}$ , because V is a solution of (17), and because the inf and sup can be interchanged in (17), we have the inequality

<span id="page-41-0"></span>
$$\partial_s V + \mathcal{L}^{\mathbb{Q}} V \ge \phi_\delta \left( \delta^* - \hat{\delta} \right)^2 + \phi_F \left( f - \hat{F} \right)^2 - \frac{1}{2\varphi} \left( x \right)^2 , \tag{A.23}$$

<span id="page-41-2"></span><span id="page-41-1"></span>

and, following the same steps as before together with (A.23), we have, under the measure  $\mathbb{Q}$ ,

$$\mathbb{E}_{t,f,v}^{\mathbb{Q}}\left[-\phi_{\delta}\int_{t}^{T}\left(\delta_{s}^{*}-\hat{\delta}\right)^{2}\mathrm{d}s-\phi_{F}\int_{t}^{T}\left(F_{s}^{\delta^{*}}-\hat{F}\right)^{2}\mathrm{d}s+\mathcal{H}_{t,T}\left(\mathbb{Q}\,|\,\mathbb{P}\right)\right]\geq V(t,f,v)\,,$$

and because this is true for all  $\mathbb{Q} \in \mathcal{Q}$ , we write

$$\inf_{\mathbb{Q}\in\mathbf{Q}}\mathbb{E}_{t,f,v}^{\mathbb{Q}}\left[-\phi_{\delta}\int_{t}^{T}\left(\delta_{s}^{*}-\hat{\delta}\right)^{2}\mathrm{d}s-\phi_{F}\int_{t}^{T}\left(F_{s}^{\delta^{*}}-\hat{F}\right)^{2}\mathrm{d}s+\mathcal{H}_{t,T}\left(\mathbb{Q}\,|\,\mathbb{P}\right)\right]\geq V(t,f,v)$$

$$\sup_{\delta\in\mathcal{A}_{t,T}}\inf_{\mathbb{Q}\in\mathbf{Q}}\mathbb{E}_{t,f,v}^{\mathbb{Q}}\left[-\phi_{\delta}\int_{t}^{T}\left(\delta_{s}-\hat{\delta}\right)^{2}\mathrm{d}s-\phi_{F}\int_{t}^{T}\left(F_{s}^{\delta}-\hat{F}\right)^{2}\mathrm{d}s+\mathcal{H}_{t,T}\left(\mathbb{Q}\,|\,\mathbb{P}\right)\right]\geq V(t,f,v), \quad (A.24)$$

which completes the second part of the proof.

Combine (A.22) and (A.24) to obtain the desired result.