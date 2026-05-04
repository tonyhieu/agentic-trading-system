## **Market Microstructure Invariance and Stock Market Crashes**

Albert S. Kyle and Anna A. Obizhaeva

University of Maryland

**Conference on Instabilities in Financial Markets Pisa, Italy October, 18, 2012**

#### **Basic Idea**

Market microstructure invariance can be used to explain stock market crashes:

- I Market microstructure invariance generates predictions about "bet size" and "price impact."
- I Using portfolio transition data, Kyle and Obizhaeva (2011a,b) fits distribution of bet size, market impact cost, and bid-ask spread costs, to markets for individual stocks.
- I When the entire stock market is viewed as one big market, the parameter estimates for individual stocks generate reasonable predictions about price declines and bet size for stock market crashes.

#### **Two Types of Market Crashes**

There are two types of market crashes:

- I **Banking Crises and Sovereign Defaults**: Associated with collapse of the banking system, exchange rate crises, currency collapse, and bouts of high inflation. Documented by Reinhart and Rogoff(2009);
- I **Stock Market Crashes**: Crashes or panics triggered by execution of large "bets." Are short-lived if followed by appropriate government policy.

#### **Market Crashes Triggered by Bets**

We consider **five market crashes** triggered by large bets. Two market crashes are triggered by bets from correlated trades of multiple entities based on the same underlying motivation.

**1929 Market Crash:** Margin calls resulted in massive selling of stocks and reductions in loans to finance margin purchases.

**1987 Market Crash:** "Portfolio Insurers" sold large quantities of stock index future contracts. Documented in The Brady Commission report (1988).

## **Market Crashes Triggered by Bets**

Three other market crashes are triggered by bets executed by one large entity:

**1987 George Soros:** Three days after the 1987 crash, the futures market declined by 20% at the open. George Soros had executed a large sell order and later sued his broker for an excessively expensive order execution.

**2008 SocG´en:** Societe Generale liquidated billions of Euros in stock index future positions accumulated by rogue trader Jerome Kerviel.

**2010 Flash Crash:** A joint study by the CFTC and SEC identified approximately \$4 billion in sales of futures contracts by one entity as a trigger for the event.

## **Conventional Wisdom and Invariance**

**Miller, Scholes, Fama, Leland and Rubinstein:** Conventional wisdom holds that prices react to changes in fundamental information, not to the price pressure resulting from trades by individual investors. In competitive markets, investors have minimal private information and their trades have minuscule price impact. The CAPM implies that the demand for market indices is very elastic.

The conventional wisdom usually assumes that trading one percent of market capitalization move prices by one percent.

#### **Conventional Wisdom and Invariance**

For example, Merton H. Miller (1991) wrote about the 1987 crash:

*"Putting a major share of the blame on portfolio insurance for creating and overinflating a liquidity bubble in 1987 is fashionable, but not easy to square with all relevant facts . . .. No study of price-quantity responses of stock prices to date supports the notion that so large a price increase (about 30 percent) would be required to absorb so modest (1 to 2 percent) a net addition to the demand for shares."*

We disagree: Large trades, even those known to have no information content such as the margin sales of 1929 or the portfolio insurance sales in 1987, do have large effect of prices.

#### **Animal Spirits and Invariance**

**Keynes (1936), Shiller and Akerlof (2009):** Animal spirits holds that price fluctuations occur as a result of random changes in psychology, which may not be based on information or rationality.

We disagree: Large crashes are neither random nor unpredictable; they are often discussed before crashes occur. The flash crashes were unpredictable, but prices rapidly mean-reverted.

#### **Main Results**

Our paper examines these five crash events from the perspective of **market microstructure invariance**, a conceptual framework developed by Kyle and Obizhaeva (2011a).

**Main Result**: Given the information about the dollar magnitudes of potential selling pressure (known before crashes), invariance would have made it possible to generate reasonable predictions of the size of the future declines.

Therefore, invariance can be a useful tool for monitoring the economy for systemic risks.

#### **Market Microstructure Invariance**

Market microstructure invariance suggests that the business time is faster for active stocks and slower for inactive stocks.

- I **For active stocks** (with high trading volume and high volatility), trading games are played at a **fast pace**.
- I **For inactive stocks** (low trading volume and low volatility), trading games are played at a **slow pace**.

Trading games are the same other than the speed at which they are played.

- I Main Invariance Principle: **"Bet size" in "business time" is the same across assets.**
- I Related Invariance Concepts: Price impact costs and bid-ask spread of executing bets are the same across assets.

#### **Estimation of Market Depth**

Market depth formula from Kyle (1985):

$$\lambda = \frac{\sigma_V}{\sigma_U}$$

- I Asserts price fluctuations result from linear price impact of order flow imbalances.
- I Numerator is "easy" to estimate from data on price volatility.
- I Denominator is harder to estimate. It is related to trading volume, but how? Market microstructure provides an identifying restriction which relates trading activity to the standard deviation of order flow imbalances.

#### **"Numerator"**

"Easy solution": *σ<sup>V</sup>* = *P · ψ · σ* = *P · σ*¯

- <sup>I</sup> *σ<sup>V</sup>* = standard deviation of daily price changes in dollars per share
- I *P* = stock price
- I *σ* = close-to-close expected standard deviation of log returns
- I *ψ* <sup>2</sup> = fraction of variance resulting from trading, not announcements (assume *ψ* = 1 for simplicity)
- I *σ*¯ = "trading volatility"

## **"Denominator": Reduced Form Approach**

As a rough approximation for short periods of time, we assume that orders arrive according to a compound Poisson process with **order arrival rate** *γ* and **order size** having a distribution represented by a random variable *Q*˜ .

Both *Q*˜ and *γ* vary across stocks.

The arrival rate *γ*, which measures market "velocity," is proportional to the speed with which business time passes.

#### **Order Flow Imbalances**

Standard deviation of order flow imbalances: *σ<sup>U</sup>* = *γ* 1*/*2 *·* (*EQ*˜ <sup>2</sup> ) 1*/*2 Define *V*¯ = *γ · E|Q*˜ *|* = *V/*(*ζ/*2), where pk:

- <sup>I</sup> *V*¯ = "expected daily bet volume"
- I *V* = Expected daily share volume
- I *ζ* = "intermediation multiplier"

Market impact (percent of stock value traded) given by

$$\frac{\lambda \cdot X}{P} = \frac{\sigma_V}{\sigma_U} \frac{X}{P} = \gamma^{-1/2} \bar{\sigma} \cdot \frac{X}{(E\tilde{Q}^2)^{1/2}}.$$
 (1)

#### **Bets**

We think of **orders** as **bets** whose size is measured by dollar standard deviation over time.

Bet size over a calendar day:

$$\tilde{B} = P \cdot \tilde{Q} \cdot \sigma$$

Bet size *B*˜ measures the standard deviation of the mark-to-market gains per calendar day, conditional on number of shares *Q*˜ . Bet size increases as **a square root** with **time**.

#### **Volatility in Business Time**

Let *σ*<sup>0</sup> denote returns volatility in business time:

$$\sigma_0 = \sigma/\gamma^{1/2}$$

Bet size can be written

$$\tilde{B} = P \cdot \tilde{Q} \cdot \sigma_0 \cdot \gamma^{1/2}$$

Bet size is proportional to the square root of the rate *γ* at which business time passes.

#### **Trading Game Invariance**

"Trading game invariance" is the hypothesis that bet size is constant when measured in units of business time, i.e., the distribution of the random variable

$$\tilde{I} \sim \tilde{B} \cdot \gamma^{-1/2} = P \cdot \tilde{Q} \cdot \sigma \cdot \gamma^{-1/2} = P \cdot \tilde{Q} \cdot \sigma_0$$

does not vary across stocks or across time.

Bet risk in calendar time remains proportional to the square root of the rate *γ* at which business time passes:

$$\tilde{B} = \gamma^{1/2} \cdot \tilde{I}$$

## **Trading Activity**

Stocks differ in their **"Trading Activity"** *W* , or a measure of gross risk transfer, defined as dollar volume adjusted for volatility *σ*:

$$W = V \cdot P \cdot \sigma = \zeta/2 \cdot \gamma \cdot \mathsf{E}\{|\tilde{B}|\}.$$

Execution of bets induces extra volume; *ζ* adjusts for non-bet volume; we might assume *ζ* is constant and equal to two.

#### **Key Result**

Trading game invariance implies trading activity is proportional to *γ* 3*/*2 :

$$W = \zeta/2 \cdot \gamma^{3/2} \cdot E\{|\tilde{I}|\}.$$

Therefore

$$\gamma \propto W^{2/3}$$

and

$$\tilde{B} \propto W^{1/3} \cdot \tilde{I}$$

.

#### Market Microstructure Invariance - Intuition

#### Benchmark Stock with Volume $V^*$ $(\gamma^*, \quad \tilde{Q}^*)$

![](_page_19_Picture_2.jpeg)

Avg. Order Size  $\tilde{Q}^*$  as fraction of  $V^* = 1/4$ 

Market Impact of 
$$1/4 V^*$$
  
= 200 bps /  $4^{1/2}$  = 100 bps

Stock with Volume  $V = 8 \cdot V^*$  $(\gamma = \gamma^* \cdot 4, \quad \tilde{Q} = \tilde{Q}^* \cdot 2)$ 

![](_page_19_Picture_7.jpeg)

Market Impact of 1/16 V = 200 bps /  $(4 \cdot 8^{2/3})^{1/2} = 50$  bps

Avg. Order Size  $\tilde{Q}$  as fraction of V =  $1/16 = 1/4 \cdot 8^{-2/3}$ 

Market Impact of 1/4 V=  $4 \cdot 50 \text{ bps} = 100 \text{ bps} \cdot 8^{1/3}$ 

 $\begin{array}{l} \textbf{Spread} \\ = \mathsf{k} \ \mathsf{bps} \cdot \textcolor{red}{8^{-1/3}} \end{array}$ 

#### **Liquidity and Velocity**

I "Velocity":

$$\gamma = \text{const} \cdot W^{2/3} = \text{const} \cdot [P \cdot V \cdot \sigma]^{2/3}$$

<sup>I</sup> Cost of Converting Asset to Cash = 1*/L*\$ :

$$L_{\S} = const \cdot \gamma^{-1/2} \cdot \bar{\sigma} = const \cdot \left[ \frac{P \cdot V}{\sigma^2} \right]^{1/3}$$

<sup>I</sup> Cost of Transferring a Risk = 1*/L<sup>σ</sup>*

$$L_{\sigma} = \text{const} \cdot W^{-1/3} = \text{const} \cdot [P \cdot V \cdot \sigma]^{-1/3}$$

#### **Invariance: Two Ways to Measure Market Depth**

Use data on size of bets:

$$\frac{\tilde{Q}}{\bar{V}} \sim (\bar{\sigma}P\bar{V})^{-2/3} \cdot E|\tilde{I}|^{-1/3} \cdot \tilde{I} = W^{-2/3} \cdot E|\tilde{I}|^{-1/3} \cdot \tilde{I}.$$
 (2)

Use market impact formula:

$$\frac{\lambda X}{P} = (P\bar{V})^{1/3} \cdot \bar{\sigma}^{4/3} \cdot \frac{X}{V} \cdot \frac{E|\tilde{I}|^{2/3}}{(E[\tilde{I}^2])^{1/2}} = W^{1/3} \cdot \bar{\sigma} \cdot \frac{X}{V} \cdot \frac{E|\tilde{I}|^{2/3}}{(E[\tilde{I}^2])^{1/2}}.$$
(3)

#### **Testing - Portfolio Transition Data**

The empirical implications of the three proposed models are tested using a proprietary dataset of **portfolio transitions**.

- I Portfolio transition occurs when an old (legacy) portfolio is replaced with a new (target) portfolio during replacement of fund management or changes in asset allocation.
- I Our data includes 2,680+ portfolio transitions executed by a large vendor of portfolio transition services over the period from 2001 to 2005.
- I Dataset reports executions of 400,000+ orders with average size of about 4% of ADV.

## **Invariance and Bet Size**

- I Kyle and Obizhaeva (2011b) use portfolio transition data to measure distribution of bet size.
- I Assume portfolio transition trades are representative "bets".

#### Distributions of Order Sizes

![](_page_24_Figure_1.jpeg)

Trading game invariance works well for **entire distributions** of order sizes. These distributions are approximately **log-normal**.

#### **Tests for Orders Size - Design**

Three models differ only in their predictions about **parameter** *a*0.

- <sup>I</sup> **Model of Trading Game Invariance:** *a*<sup>0</sup> = *−*2*/*3.
- <sup>I</sup> Model of Invariant Bet Frequency: *a*<sup>0</sup> = 0.
- <sup>I</sup> Model of Invariant Bet Size: *a*<sup>0</sup> = *−*1.

We estimate the parameter *a*<sup>0</sup> to examine which of three models make the most reasonable assumptions.

## **Tests for Order Size: Results**

|    |          | NYSE     |          | NASDAQ   |          |
|----|----------|----------|----------|----------|----------|
|    | All      | Buy      | Sell     | Buy      | Sell     |
| q¯ | -5.67*** | -5.68*** | -5.63*** | -5.75*** | -5.65*** |
|    | (0.017)  | (0.022)  | (0.018)  | (0.033)  | (0.031)  |
| a  | -0.63*** | -0.63*** | -0.60*** | -0.71*** | -0.61*** |
| 0  | (0.008)  | (0.010)  | (0.008)  | (0.019)  | (0.012)  |

- <sup>I</sup> **Model of Trading Game Invariance:** *a*<sup>0</sup> = *−*2*/*3.
- I Model of Invariant Bet Frequency: *a*<sup>0</sup> = 0.
- <sup>I</sup> Model of Invariant Bet Size: *a*<sup>0</sup> = *−*1.

*<sup>∗∗∗</sup>*is 1%-significance, *∗∗*is 5%-significance, *<sup>∗</sup>* is 10%-significance.

#### **Calibration: Direct Estimate of Market Impact**

Using order size data but not execution price data, market impact can be calibrated directly from formula

$$\lambda = \frac{\sigma_V}{\sigma_U} = \frac{\psi \sigma P}{\zeta/2 \cdot [\gamma E\{\tilde{Q}^2\}]^{1/2}}$$

using assumptions such as *ζ* = 2 and *ψ* = 1. (This is consistent with Kyle (1985) linear impact formula *λ* = *σ<sup>V</sup> /σU*.)

I Under the assumptions *ζ* = 2 and *ψ* = 1*.*10, the results are the same as estimates based on implementation shortfall.

#### **Portfolio Transitions and Trading Costs**

**"Implementation shortfall"** is the difference between actual trading prices (average execution prices) and hypothetical prices resulting from "paper trading" (price at previous close).

There are **several problems** usually associated with using implementation shortfall to estimate transactions costs. Portfolio transition orders avoid most of these problems.

#### **Problem I with Implementation Shortfall**

Implementation shortfall is a **biased estimate** of transaction costs when it is based on price changes and executed quantities, because these quantities themselves are often correlated with price changes in a manner which biases transactions costs estimates.

**Example A:** Orders are often canceled when price runs away. Since these non-executed, high-cost orders are left out of the sample, we would underestimate transaction costs.

**Example B:** When a trader places an order to buy stock, he has in mind placing another order to buy more stock a short time later.

For **portfolio transitions**, this problem does not occur: Orders are not canceled. The timing of transitions is somewhat exogenous.

#### **Problems II with Implementation Shortfall**

The second problem is **statistical power**.

**Example:** Suppose that 1% ADV has a transactions cost of 20 bps, but the stock has a volatility of 200 bps. Order adds only 1% to the variance of returns. A properly specified regression will have an R squared of 1% only!

For **portfolio transitions**, this problem does not occur: Large and numerous orders improve statistical precision.

#### **Tests For Market Impact and Spread - Design**

All three models are nested into one specification that relates **trading activity** *W* and **implementation shortfall C** for a transition order for *X* shares:

$$C_{i} \cdot \left[\frac{0.02}{\sigma}\right] = \frac{1}{2} \bar{\lambda} \cdot \left[\frac{W_{i}}{W_{*}}\right]^{\alpha_{0}} \cdot \frac{X_{i}}{(0.01)V_{i}} + \frac{1}{2} \bar{k} \cdot \left[\frac{W_{i}}{W_{*}}\right]^{\alpha_{1}} \cdot \frac{(X_{omt,i} + X_{ec,i})}{X_{i}} + \tilde{\epsilon}$$

The variables are scaled so that parameters *λ*¯ and *k*¯ measure in basis point the market impact (for 1% of daily volume *V*) and spread for a **benchmark stock** with volatility 2% per day, price \$40 per share, and daily volume of 1 million shares.

- I Spread is assumed to be paid only on shares executed externally in open markets and external crossing networks, not on internal crosses.
- I Implementation shortfall is adjusted for differences in volatility.

#### **Tests For Market Impact and Spread - Design**

The three models make different predictions about **parameters** *a*<sup>0</sup> **and** *a*1.

- <sup>I</sup> **Model of Trading Game Invariants:** *α*<sup>0</sup> = 1*/*3*, α*<sup>1</sup> = *−*1*/*3.
- <sup>I</sup> Model of Invariant Bet Frequency: *α*<sup>0</sup> = 0*, α*<sup>1</sup> = 0.
- <sup>I</sup> Model of Invariant Bet Size: *α*<sup>0</sup> = 1*/*2*, α*<sup>1</sup> = *−*1*/*2.

We estimate *a*<sup>0</sup> and *a*<sup>1</sup> to test which of three models make the most reasonable predictions.

#### **Tests For Market Impact and Spread - Results**

|                   |                     | NYSE                |                     | NASDAQ              |                     |
|-------------------|---------------------|---------------------|---------------------|---------------------|---------------------|
|                   | All                 | Buy                 | Sell                | Buy                 | Sell                |
| λ¯<br>1<br>/<br>2 | 2.85***<br>(0.245)  | 2.50***<br>(0.515)  | 2.33***<br>(0.365)  | 4.2***<br>(0.753)   | 2.99***<br>(0.662)  |
| α<br>0            | 0.33***<br>(0.024)  | 0.18***<br>(0.045)  | 0.33***<br>(0.054)  | 0.33***<br>(0.053)  | 0.35***<br>(0.045)  |
| k¯<br>1<br>/<br>2 | 6.31***<br>(1.131)  | 14.99***<br>(2.529) | 2.82*<br>(1.394)    | 8.38*<br>(3.328)    | 3.94**<br>(1.498)   |
| α<br>1            | -0.39***<br>(0.025) | -0.19***<br>(0.045) | -0.46***<br>(0.061) | -0.36***<br>(0.061) | -0.45***<br>(0.047) |

- <sup>I</sup> Model of Trading Game Invariance: *α*<sup>0</sup> = 1*/*3*, α*<sup>1</sup> = *−*1*/*3.
- I Model of Invariant Bet Frequency: *α*<sup>0</sup> = 0*, α*<sup>1</sup> = 0.
- <sup>I</sup> Model of Invariant Bet Size: *α*<sup>0</sup> = 1*/*2*, α*<sup>1</sup> = *−*1*/*2.

*<sup>∗∗∗</sup>*is 1%-significance, *∗∗*is 5%-significance, *<sup>∗</sup>* is 10%-significance.

#### **Calibration: Transactions Cost Formula**

For a **benchmark stock**, half market impact  $\frac{1}{2}\lambda^*$  is 2.89 basis points and half-spread  $\frac{1}{2}k^*$  is 7.90 basis points.

The Model of Market Microstructure Invariants extrapolates these estimates and allows us to calculate **expected trading costs** for any order of X shares for any security using a simple formula:

$$C(X) = \frac{1}{2}\lambda^* \left(\frac{W}{(40)(10^6)(0.02)}\right)^{1/3} \frac{\sigma}{0.02} \frac{X}{(0.01)V} + \frac{1}{2}k^* \left(\frac{W}{(40)(10^6)(0.02)}\right)^{-1/3} \frac{\sigma}{0.02},$$

where trading activity  $W = \sigma \cdot P \cdot V$ 

- $\triangleright$   $\sigma$  is the expected daily volatility,
- V is the expected daily trading volume in shares,
- ▶ *P* is the price.

#### **Calibration: Implications of Log-Normality for Volume and Volatility**

Standard deviation of log of bet size is 2*.*501*/*<sup>2</sup> .

- I Implies a one standard deviation increase in bet size is a factor of about 4*.*85.
- I Implies 50% of trading volume generated by largest 5*.*71% of bets.
- I Implies 50% of returns variance generated by largest 0*.*08% of bets.

#### **Calibration: Bet Size and Trading Activity**

Benchmark stock has \$40 million daily volume and 2% daily returns standard deviation. For the benchmark stock, empirical results imply:

- I Average bet size is 0.34% of expected daily volume.
- I Benchmark stock has about 85 bets per day.
- I Median bet size is \$136,000; average bet size is \$472,000.
- I Order imbalances are 38% of daily trading volume.
- I Four standard deviation event is about \$1 billion bet.

These "predictions" are quite reasonable! Suggests invariance applies to market as a whole.

#### **Extrapolation to Market as a Whole**

Market is stock index futures market. Increase size of market by a factor of about 1000 (2000X volume, 1/2 volatility):

- I Futures market has has about 8500 bets per day.
- I Median bet size is \$1.36 million; average bet size is \$4.72million.
- I Order imbalances are 3.8% of daily trading volume.

### **Calibration: "Time Change" Literature**

"Time change" is that idea that a larger than usual number of independent price fluctuations results from business time passing faster than calendar time.

- I Mandelbrot and Taylor (1967): Stable distributions with kurtosis greater than normal distribution implies infinite variance for price changes.
- I Clark (1973): Price changes result from log-normal with time-varying variance, implying finite variance to price changes.
- I Microstructure invariance: Kurtosis in returns results from rare, very large bets, due to high variance of log-normal. Caveat: Large bets may be executed very slowly, e.g., over weeks.
- I Econophysics: Gabaix et al. (2006); Farmer, Bouchard, Lillo (2009). Right tail of distribution might look like a power law.

#### **Market Temperature**

Derman (2002) defines market temperature  $\chi$  as  $\chi = \sigma \cdot \gamma^{1/2}$ . Standard deviation of order imbalances is  $P \cdot \sigma_U = [\gamma \cdot E\{\tilde{Q}^2\}]^{1/2}$ .

- ▶ Product of temperature and order imbalances proportional to trading activity:  $P\sigma_U \cdot \chi \propto W$
- ▶ Invariance implies temperature  $\propto (PV)^{1/3}\sigma^{4/3}$ .
- ▶ Invariance implies expected market impact cost of an order  $\propto (PV)^{1/3}\sigma^{4/3}$ .

Therefore invariance implies temperature proportional to market impact cost of an order.

#### Implication: Transactions Cost Formula

Market Microstructure Invariance suggests a simple formula for calculation of expected transaction costs for any order of X shares for any security with a current stock price P dollars, expected trading volume V shares per calendar day, and daily volatility  $\sigma$ :

$$\frac{\Delta P(X)}{P} = \exp\left[\bar{\lambda}/10^4 \cdot \left(\frac{P \cdot V}{40 \cdot 10^6}\right)^{1/3} \cdot \left(\frac{\sigma}{0.02}\right)^{4/3} \cdot \frac{X}{(0.01)V}\right] - 1.$$

where  $\frac{1}{2}\bar{\lambda} = 2.89$  (standard error 0.195) is calibrated based on **portfolio transition trades** in Kyle and Obizhaeva (2011b).

#### **Stock Market Crashes: Implementation Issues**

To apply microstructure invariance, several implementation issues need to be discussed:

- I **Boundary of the market:** Different securities and futures contracts, traded on various exchanges, may share the same fundamentals or be correlated. How to aggregate estimates across economically related markets? How to identify market boundaries?
- I **Permanent vs. transitory price impact** Invariance formula assumes that orders are executed in some "natural" units of time. If execution is speeded up, then invariance formulas may underestimate price impact.
- I **Inputs:** Invariance formulas requires expected volume and expected volatility as inputs. Expected volume and volatility may be higher than historical levels during extreme events.
- I **Other considerations:** Invariance formula predicts impact of sales by particular group of traders. Other events may influence prices at the same time, including arrival of news and trading by other traders.

#### Facts about the stock market in 1929:

- I In 1920s, many Americans became heavily invested into stocks (as in late 1990s), with a significant portion of investments made in margin accounts.
- I To finance margin accounts, brokers relied on broker loans, pooling purchased securities to pledge as collateral (similar to shadow banking system in 2000s).
- I Lenders were banks (except for NY banks after 1927), investment trusts, corporations, and foreign institutions.
- I After doubling in value during the two years prior to Sept 1929, the Dow fell by 9% before Oct 24, 1929. This decline led to liquidations of stocks in margin accounts.
- I During Oct 24 through Oct 30, **the Dow fell by 25%**. The slide continued for three more weeks. From Sept 25 to Dec 25, **the Dow fell by 48%**.

![](_page_43_Figure_1.jpeg)

![](_page_44_Figure_1.jpeg)

**10/23-10/30: Margin sales of \$1.181 billion. 09/25-12/25: Margin sales of \$4.348 billion.**

#### Facts about 1929 stock market crash:

- I **Volatility** was about 2.00%.
- I **Trading volume** was **\$342.29 million** per day.
- I Prior to 1935, the volume reported on the ticker did not include "odd-lot transactions and "stopped-stock" transactions (about 30% percent of the "reported" volume), so adjust reported volume by 10*/*7.
- I Inflation makes 1929 dollar worth more than 2001-2005 dollar: \$1 in 1929 to \$9.42 in 2005.
- I During 10/24-10/29, the Dow declined by **24%** from 305.85 to 230.07. During 9/25-12/25, the Dow declined by **34%** from 305.85 to 230.07.

Invariance formula implies decline of **49.22%** during 10/24-10/30,

$$1 - \text{exp}\, \Big[ -\frac{5.78}{10^4} \cdot \left(\frac{488.98 \cdot 10^6 \cdot 9.42}{(40)(10^6)}\right)^{1/3} \cdot \left(\frac{0.0200}{0.02}\right)^{4/3} \cdot \frac{1.181 \cdot 10^9}{(0.01)(488.98 \cdot 10^6)} \Big]$$

Invariance formula implies decline of **91.75%** during 09/25-12/25,

$$1- \exp \Big[-\frac{5.78}{10^4} \cdot \left(\frac{488.98 \cdot 10^6 \cdot 9.42}{(40)(10^6)}\right)^{1/3} \cdot \left(\frac{0.0200}{0.02}\right)^{4/3} \cdot \frac{4.348 \cdot 10^9}{(0.01)(488.98 \cdot 10^6)} \Big] + \frac{1}{10^6} \cdot \frac{1}{10^6} \cdot \frac{1}{10^6} \cdot \frac{1}{10^6} \cdot \frac{1}{10^6} \cdot \frac{1}{10^6} \cdot \frac{1}{10^6} \cdot \frac{1}{10^6} \cdot \frac{1}{10^6} \cdot \frac{1}{10^6} \cdot \frac{1}{10^6} \cdot \frac{1}{10^6} \cdot \frac{1}{10^6} \cdot \frac{1}{10^6} \cdot \frac{1}{10^6} \cdot \frac{1}{10^6} \cdot \frac{1}{10^6} \cdot \frac{1}{10^6} \cdot \frac{1}{10^6} \cdot \frac{1}{10^6} \cdot \frac{1}{10^6} \cdot \frac{1}{10^6} \cdot \frac{1}{10^6} \cdot \frac{1}{10^6} \cdot \frac{1}{10^6} \cdot \frac{1}{10^6} \cdot \frac{1}{10^6} \cdot \frac{1}{10^6} \cdot \frac{1}{10^6} \cdot \frac{1}{10^6} \cdot \frac{1}{10^6} \cdot \frac{1}{10^6} \cdot \frac{1}{10^6} \cdot \frac{1}{10^6} \cdot \frac{1}{10^6} \cdot \frac{1}{10^6} \cdot \frac{1}{10^6} \cdot \frac{1}{10^6} \cdot \frac{1}{10^6} \cdot \frac{1}{10^6} \cdot \frac{1}{10^6} \cdot \frac{1}{10^6} \cdot \frac{1}{10^6} \cdot \frac{1}{10^6} \cdot \frac{1}{10^6} \cdot \frac{1}{10^6} \cdot \frac{1}{10^6} \cdot \frac{1}{10^6} \cdot \frac{1}{10^6} \cdot \frac{1}{10^6} \cdot \frac{1}{10^6} \cdot \frac{1}{10^6} \cdot \frac{1}{10^6} \cdot \frac{1}{10^6} \cdot \frac{1}{10^6} \cdot \frac{1}{10^6} \cdot \frac{1}{10^6} \cdot \frac{1}{10^6} \cdot \frac{1}{10^6} \cdot \frac{1}{10^6} \cdot \frac{1}{10^6} \cdot \frac{1}{10^6} \cdot \frac{1}{10^6} \cdot \frac{1}{10^6} \cdot \frac{1}{10^6} \cdot \frac{1}{10^6} \cdot \frac{1}{10^6} \cdot \frac{1}{10^6} \cdot \frac{1}{10^6} \cdot \frac{1}{10^6} \cdot \frac{1}{10^6} \cdot \frac{1}{10^6} \cdot \frac{1}{10^6} \cdot \frac{1}{10^6} \cdot \frac{1}{10^6} \cdot \frac{1}{10^6} \cdot \frac{1}{10^6} \cdot \frac{1}{10^6} \cdot \frac{1}{10^6} \cdot \frac{1}{10^6} \cdot \frac{1}{10^6} \cdot \frac{1}{10^6} \cdot \frac{1}{10^6} \cdot \frac{1}{10^6} \cdot \frac{1}{10^6} \cdot \frac{1}{10^6} \cdot \frac{1}{10^6} \cdot \frac{1}{10^6} \cdot \frac{1}{10^6} \cdot \frac{1}{10^6} \cdot \frac{1}{10^6} \cdot \frac{1}{10^6} \cdot \frac{1}{10^6} \cdot \frac{1}{10^6} \cdot \frac{1}{10^6} \cdot \frac{1}{10^6} \cdot \frac{1}{10^6} \cdot \frac{1}{10^6} \cdot \frac{1}{10^6} \cdot \frac{1}{10^6} \cdot \frac{1}{10^6} \cdot \frac{1}{10^6} \cdot \frac{1}{10^6} \cdot \frac{1}{10^6} \cdot \frac{1}{10^6} \cdot \frac{1}{10^6} \cdot \frac{1}{10^6} \cdot \frac{1}{10^6} \cdot \frac{1}{10^6} \cdot \frac{1}{10^6} \cdot \frac{1}{10^6} \cdot \frac{1}{10^6} \cdot \frac{1}{10^6} \cdot \frac{1}{10^6} \cdot \frac{1}{10^6} \cdot \frac{1}{10^6} \cdot \frac{1}{10^6} \cdot \frac{1}{10^6} \cdot \frac{1}{10^6} \cdot \frac{1}{10^6} \cdot \frac{1}{10^6} \cdot \frac{1}{10^6} \cdot \frac{1}{10^6} \cdot \frac{1}{10^6} \cdot \frac{1}{10^6} \cdot \frac{1}{10^6} \cdot \frac{1}{10^6} \cdot \frac{1}{10^6} \cdot \frac{1}{10^6} \cdot \frac{1}{10^6} \cdot \frac{1}{10^6} \cdot \frac{1}{10^6} \cdot \frac{1}{10^6} \cdot \frac{1}{10^6} \cdot \frac{1}{10^6} \cdot \frac{1}{10^6} \cdot \frac{1}{10^6} \cdot \frac{1}{10^6} \cdot \frac{1}{10^6} \cdot \frac{1}{10^6} \cdot \frac{1}{10^6} \cdot \frac{1}{10^6} \cdot \frac{1}{10^6} \cdot \frac{1}{10^6} \cdot \frac{1}{10^6} \cdot \frac{1}{10^6} \cdot \frac{$$

Invariance suggests **margin sales** should have had a larger market impact than the actual price changes of **24%** during 10/24-10/30 and **34%** during 9/25-12/25.

*.*

#### **1929 Stock Market Crash - Robustness**

|                                       |                  |                  | Months Preceding 24 October 1929 |                  |                   |                  |
|---------------------------------------|------------------|------------------|----------------------------------|------------------|-------------------|------------------|
| N:                                    | 1                | 2                | 3                                | 4                | 6                 | 12               |
| ADV (in 1929-\$M)<br>Daily Volatility | 488.98<br>0.0200 | 507.08<br>0.0159 | 479.65<br>0.0145                 | 469.45<br>0.0128 | 4425.47<br>0.0119 | 429.06<br>0.0111 |
| Sales 10/24-10/30 (%ADV)              | 242%             | 233%             | 246%                             | 252%             | 278%              | 275%             |
| Price Impact 10/24-10/30              | 49.22%           | 38.67%           | 36.05%                           | 32.04%           | 31.05%            | 28.72%           |
| Sales 9/25-12/25 (%ADV)               | 1270%            | 1225%            | 1295%                            | 1323%            | 1460%             | 1448%            |
| Price Impact 9/25-12/25               | 91.75%           | 83.47%           | 80.71%                           | 75.87%           | 74.56%            | 71.25%           |

The actual price changes were **24%** during 10/24-10/30 and **34%** during 9/25 and 12/25. The conventional wisdom predicts price decline of **1.36%** and **4.99%**, respectively.

#### Facts about 1987 stock market crash:

- I **Volatility** during crash was about 1.35%.
- I **Trading volume** on October 19 was **\$20 billion** (\$10.37 billion futures plus \$10.20 billion stock).
- I From Wednesday to Tuesday, **portfolio insurers** sold **\$14 Billion** (\$10.48 billion in the S&P 500 index futures and \$3.27 billion in the NYSE stocks in 1987 dollars).
- I Inflation makes 1987 dollar worth more than 2001-2005 dollar: \$1 in 1987 to \$1.54 in 2005.
- I From Wednesday to Tuesday, **S&P 500 futures** declined from 312 to 185, a decline of **40%** (including bad basis). **Dow** declined from 2500 to 1700, a decline of **32%**.

Our market impact formula implies decline of **19.12%**,

$$1-\exp\Big[-5.78/10^4\cdot\left(\frac{(10.37+10.20)\cdot 10^9\cdot 1.54}{40\cdot 10^6}\right)^{1/3}\cdot\left(\frac{0.0135}{0.02}\right)^{4/3}\cdot\frac{(10.48+3.27)\cdot 10^9}{(0.01)(10.37+10.20)\cdot 10^9}\Big]$$

Invariance suggests **portfolio insurance selling** had market impact smaller than the actual price change of **32%** in stock market and **40%** in futures market.

#### **1987 Stock Market Crash - Robustness**

|                                                                   |                          |                          |                          | Months Preceding 14 October 1987 |                          |                        |
|-------------------------------------------------------------------|--------------------------|--------------------------|--------------------------|----------------------------------|--------------------------|------------------------|
| N:                                                                | 1                        | 2                        | 3                        | 4                                | 6                        | 12                     |
| S&P 500 ADV (1987-\$B)<br>NYSE ADV (1987-\$B)<br>Daily Volatility | 10.37<br>10.20<br>0.0135 | 11.29<br>10.44<br>0.0121 | 11.13<br>10.48<br>0.0107 | 10.12<br>10.16<br>0.0102         | 10.62<br>10.04<br>0.0112 | 9.85<br>9.70<br>0.0111 |
| Sell Orders as % ADV                                              | 66.84%                   | 63.28%                   | 63.65%                   | 67.82%                           | 66.53%                   | 70.33%                 |
| Price Impact of Sell Orders<br>Price Impact of Imbalances         | 19.12%<br>15.75%         | 16.20%<br>13.30%         | 14.00%<br>11.47%         | 13.59%<br>11.13%                 | 15.10%<br>12.39%         | 15.60%<br>12.80%       |

The actual price change was **32%** in stock market and **40%** in futures market. The conventional wisdom predicts price declines of **0.51%** for portfolio insurers' order imbalances and **0.63%** for their sales.

## **Soros's Trades in 1987**

Facts about Soros's trades after 1987 stock market crash:

- I **Volatility** prior to October 22 was about 8.63%.
- I **Trading volume** prior to October 22 was **\$13.52 billion** in futures.
- I At the open of October 22, 1987, George Soros sold **2,400 contracts of S&P 500 futures** at a limit price of 200. A broker oversold **651 contracts**. Later in the morning, a pension plan sold **2,478 contracts**.
- I Inflation makes 1987 dollar worth more than 2001-2005 dollar: \$1 in 1987 to \$1.54 in 2005.
- I Price declined by **22%** from 258 at close of October 21, 1987, to 200 and then rebounded, over the next two hours, to the levels of the previous day's close.
- I Soros sued a broker for tipping off other traders and executing order at too low prices.

#### **Soros's Trades in 1987**

Our market impact formula implies decline of **7.21%**,

$$1 - exp\, \Big[ -\frac{5.78}{10^4} \cdot \left(\frac{13.52 \cdot 10^9 \cdot 1.54}{40 \cdot 10^6}\right)^{1/3} \cdot \left(\frac{0.0863}{0.02}\right)^{4/3} \cdot \frac{309.60 \cdot 10^6}{(0.01)(13.52 \cdot 10^9)} \Big].$$

Invariance suggests somewhat smaller price impact relative to the actual price change of **22%**.

#### **Soros's Trades in 1987 - Robustness**

|                                                    |                          |                          | Months Preceding 22 October 1987 |                         |                         |                         |
|----------------------------------------------------|--------------------------|--------------------------|----------------------------------|-------------------------|-------------------------|-------------------------|
| N:                                                 | 1                        | 2                        | 3                                | 4                       | 6                       | 12                      |
| S&P 500 Fut ADV (1987-\$B)<br>Daily Volatility     | 13.52<br>0.0863          | 11.72<br>0.0622          | 11.70<br>0.0502                  | 10.99<br>0.0438         | 10.75<br>0.0365         | 10.04<br>0.0271         |
| 2,400 contracts as %ADV                            | 2.29%                    | 2.64%                    | 2.65%                            | 2.82%                   | 2.88%                   | 3.08%                   |
| Price Impact A<br>Price Impact B<br>Price Impact C | 7.21%<br>9.07%<br>15.83% | 5.18%<br>6.54%<br>11.53% | 3.92%<br>4.96%<br>8.80%          | 3.42%<br>4.32%<br>7.70% | 2.73%<br>3.45%<br>6.17% | 1.93%<br>2.45%<br>4.40% |

Note: (A) 2,400 contracts; (B) 2*,* 400 + 651 contracts; (C) 2*,* 400 + 651 + 2*,* 478 contracts. The actual price change was **22%**. The conventional wisdom predicts price declines of **0.01%**, **0.02%**, and **0.03%**, respectively.

#### **Fraud at Soci´et´e G´en´erale, January 2008**

#### Facts about a fraud:

- I From Jan 21 to Jan 23, a fraudulent position of J´erˆome Kerviel had to be liquidated: e**30 billion** in Euro STOXX50 futures, e**18 billion** in DAX futures, and e**2 billion** in FTSE futures.
- I **Trading volume** was e**69.51 billion** in seven largest European exchanges and e**110.98 billion** in ten most actively traded Euro pean index futures.
- I **Volatility** was about **1.10%** per day in Stoxx TMI.
- I Inflation makes 2008 dollar worth less than 2001-2005 dollar: \$1 in 2008 to \$0.92 in 2005.
- I Bank has reported exceptional losses of e**6.3 billion**, which were attributed to "adverse market movements" between Jan 21 and Jan 23. Broad European index Stoxx TMI declined by **9.44%** from 316.73 on January 18 to its lowest level of 286.82 on January 21. Many European markets experienced worst price declines.

#### Liquidation of Kerviel's Positions in 2008

Our market impact formula implies decline of 12.37%,

$$1-exp\,\Big[-\frac{5.78}{10^4}\cdot \left(\frac{180.49\cdot 1.4690\cdot 0.92\cdot 10^9}{40\cdot 10^6}\right)^{1/3} \left(\frac{0.0011}{0.02}\right)^{4/3} \frac{50}{(0.01)180.49}\Big].$$

Invariance suggests price impact similar in magnitude to the actual price change of 9.44%.

#### **Liquidation of Kerviel's Positions - Robustness**

|                        |        |        | Months Preceding January 18, 2008 |        |        |        |
|------------------------|--------|--------|-----------------------------------|--------|--------|--------|
| N:                     | 1      | 2      | 3                                 | 4      | 6      | 12     |
| Stk Mkt ADV (2008-eB)  | 69.51  | 66.51  | 67.37                             | 67.01  | 66.73  | 66.32  |
| Fut Mkt ADV (2008-eB)  | 110.98 | 114.39 | 118.05                            | 117.46 | 127.17 | 121.26 |
| Daily Volatility       | 0.0110 | 0.0125 | 0.0121                            | 0.0117 | 0.0132 | 0.0111 |
| Order as %ADV          | 27.70% | 27.64% | 26.97%                            | 27.11% | 25.79% | 26.66% |
| Price Impact           | 12.37% | 14.48% | 13.67%                            | 13.21% | 14.79% | 12.14% |
| Total Losses (2008-eB) | 3.19   | 3.76   | 3.54                              | 3.42   | 3.85   | 3.13   |
| Losses/Adj A (2008-eB) | 5.50   | 6.07   | 5.85                              | 5.73   | 6.16   | 5.44   |
| Losses/Adj B (2008-eB) | 7.81   | 8.38   | 8.16                              | 8.04   | 8.47   | 7.75   |

Adj A and Adj B are adjustments for losses during 12/31/2007 through 01/18/2008. The actual price change was **9.44%** in Stoxx Europe TMI. The reported losses were e**6.3 billion** relative to value on 12/31/2007. The conventional wisdom predicts price decline of **0.43%**.

# Liquidation of Kerviel's Positions - DAX, Stoxx 50, FTSE 100

|                                                                                   |               | Months | Preceding | January 1 | 8, 2008 |        |
|-----------------------------------------------------------------------------------|---------------|--------|-----------|-----------|---------|--------|
| N:                                                                                | 1             | 2      | 3         | 4         | 6       | 12     |
| EURO STOXX 50 (2008-€B) Daily Volatility Euro Stoxx 50 Order as %ADV Price Impact | 55.19         | 54.02  | 54.64     | 53.75     | 57.88   | 52.32  |
|                                                                                   | 0.0098        | 0.0110 | 0.0098    | 0.0095    | 0.0112  | 0.0099 |
|                                                                                   | 54.36%        | 55.54% | 54.90%    | 55.81%    | 51.83%  | 57.33% |
|                                                                                   | <b>13.82%</b> | 16.15% | 14.00%    | 13.63%    | 15.86%  | 14.47% |
| DAX (2008-€B)                                                                     | 32.40         | 31.86  | 33.01     | 32.40     | 35.55   | 35.80  |
| Daily Volatility                                                                  | 0.0100        | 0.0108 | 0.0096    | 0.0090    | 0.0100  | 0.0098 |
| Order as %ADV                                                                     | 55.56%        | 56.49% | 54.53%    | 55.56%    | 50.63%  | 50.28% |
| Price Impact                                                                      | <b>12.34%</b> | 13.63% | 11.55%    | 10.83%    | 11.62%  | 11.30% |
| FTSE 100 (2008-£B) Daily Volatility Order as %ADV Price Impact                    | 7.34          | 7.87   | 7.73      | 7.74      | 8.01    | 7.21   |
|                                                                                   | 0.0109        | 0.0138 | 0.0124    | 0.0119    | 0.0137  | 0.0110 |
|                                                                                   | 27.24%        | 25.41% | 25.88%    | 25.84%    | 24.97%  | 27.76% |
|                                                                                   | <b>4.75%</b>  | 6.16%  | 5.43%     | 5.12%     | 6.05%   | 4.86%  |
| Total Losses (2008-€B)                                                            | 3.35          | 3.86   | 3.31      | 3.17      | 3.62    | 3.35   |
| Losses/Adj A (2008-€B)                                                            | 5.66          | 6.17   | 5.62      | 5.48      | 5.93    | 5.66   |
| Losses/Adj B (2008-€B)                                                            | 7.97          | 8.48   | 7.92      | 7.79      | 8.24    | 7.97   |

DAX declined by 11.91%; Euro Stoxx50 by 10.50%; FTSE100 by 4.65%

## **Integrated vs. Separate Markets**

Financial markets are **integrated**. Many European markets experienced large declines during Jan 18 through Jan 22 with rapid recoveries by Jan 24.

- I The **Spanish index IBEX 35** dropped by **7.54%**, the biggest one-day fall in the history of the index (since 1992).
- I The **Italian index FTSE MIB** fell by **10.11%**.
- I The **Swedish index OMXS 30** fell by **8.63%**.
- I The **French index CAC 40** fell by **11.53%**.
- I The **Dutch index AEX** fell by **10.80%**.
- I The **Swiss Market Index** fell by **9.63%**.

Similar patterns were observed during the 1987 market crash. How to aggregate estimates across economically related markets is a question for the future research.

#### **The "Flash Crash" of May 6, 2010**

#### Facts about a fraud:

- I News media report that a large trader sold **75,000 S&P 500 E-mini contracts**. One contracts represents ownership of about \$58,200 with S&P level of 1,164 on May 5.
- I **Trading volume** was **\$132.00 billion** in S&P 500 E-mini futures and **\$161.41 billion** in stock market in 2010 dollars.
- I **Volatility** was about **1.07%** per day in the S&P 500 E-mini future. It could be higher due to European debt crisis, e.g., *σ* = 0*.*02
- I Inflation makes 2010 dollar worth less than 2001-2005 dollar: \$1 in 2010 to \$0.90 in 2005.
- I The E-mini S&P 500 futures price fell from 1,113 at 2:40 p.m. to 1,056 at 2:45 p.m., a decline of **5.12%** over a five-minute period. Pre-programmed circuit breakers stopped futures trading for five seconds. Over the next ten minutes, the market rose by about 5%.

#### **Flash Crash in May 2010**

Our market impact formula implies decline of **0.70%**,

$$1- \exp \Big[ -\frac{5.78}{10^4} \cdot \left( \frac{(132+161) \cdot 0.90 \cdot 10^9}{40 \cdot 10^6} \right)^{1/3} \cdot \left( \frac{0.0107}{0.02} \right)^{4/3} \cdot \frac{75,000 \cdot 50 \cdot 1,164}{0.01 \cdot (132+161) \cdot 10^9} \Big].$$

Invariance suggests somewhat smaller price impact relative to the actual price change of **5.12%**.

#### **Flash Crash in May 2010 - Robustness**

|                                                                         |                            |                            | Months Preceding 6 May 2010 |                            |                            |                           |
|-------------------------------------------------------------------------|----------------------------|----------------------------|-----------------------------|----------------------------|----------------------------|---------------------------|
| N:                                                                      | 1                          | 2                          | 3                           | 4                          | 6                          | 12                        |
| S&P500 Fut ADV (2010 \$B)<br>Stk Mkt ADV (2010 \$B)<br>Daily Volatility | 132.00<br>161.41<br>0.0107 | 107.49<br>146.50<br>0.0085 | 109.54<br>142.09<br>0.0078  | 112.67<br>143.03<br>0.0090 | 100.65<br>132.58<br>0.0089 | 95.49<br>129.30<br>0.0108 |
| Order as %ADV<br>Price Impact (hist<br>σ)<br>Price Impact (σ<br>= 2%)   | 1.49%<br>0.70%<br>1.60%    | 1.72%<br>0.57%<br>1.76%    | 1.73%<br>0.50%<br>1.77%     | 1.71%<br>0.61%<br>1.75%    | 1.87%<br>0.63%<br>1.86%    | 1.94%<br>0.84%<br>1.91%   |

The actual price change of the S&P 500 E-mini futures was **5.12%**. The conventional wisdom predicts price decline of **0.03%**.

#### **Summary of Five Crash Events: Actual and Predicted Price Declines**

|                     | Actual | Predicted  | Predicted    | %ADV    | %GDP   | Frequency           |
|---------------------|--------|------------|--------------|---------|--------|---------------------|
|                     |        | Invariance | Conventional |         |        |                     |
|                     |        |            |              |         |        |                     |
| 1929 Market Crash   | 25%    | 49.22%     | 1.36%        | 241.52% | 1.136% | once in 5,539 years |
| 1987 Market Crash   | 40%    | 19.12%     | 0.63%        | 66.84%  | 0.280% | once in 716 years   |
| 1987 Soros's Trades | 22%    | 7.21%      | 0.01%        | 2.29%   | 0.007% | once per month      |
| 2008 SocG´en Trades | 9.44%  | 12.37%     | 0.43%        | 27.70%  | 0.401% | once in 819 years   |
| 2010 Flash Crash    | 5.12%  | 0.50%      | 0.03%        | 1.49%   | 0.030% | several per year    |
|                     |        |            |              |         |        |                     |

#### **Discussion**

- I **Price impact predicted by invariance is large and similar to actual price changes.**
- I **The financial system in 1929 was remarkably resilient.** The 1987 portfolio insurance trades were equal to about 0.28% of GDP and triggered price impact of 32% in cash market and 40% in futures market. The 1929 margin-related sales during the last week of October were equal to 1% of GDP. They triggered price impact of 24% only.

## **Discussion - Cont'd**

- I **Speed of liquidation magnifies short-term price effects.** The 1987 Soros trades and the 2010 flash-crash trades were executed rapidly. Their actual price impact was greater than predicted by microstructure invariance, but followed by rapid mean reversion in prices.
- I **Market crashes happen too often.** The three large crash events were approximately 6 standard deviation bet events, while the two flash crashes were approximately 4.5 standard deviation bet events. Right tail appears to be fatter than predicted. The true standard deviation of underlying normal variable is not 2.50 but 15% bigger, or far right tail may be better described by a power law.

#### **Early Warning System**

**Early warning systems** may be useful and practical. Invariance can be used as a practical tool to help quantify the systemic risks which result from sudden liquidations of speculative positions.