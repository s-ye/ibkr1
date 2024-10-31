# strategies.py
from base_strategy import BaseStrategy
import pandas as pd
import matplotlib.pyplot as plt
from stoploss_takeprofit_strategy import StopLossTakeProfitStrategy


class SmaCrossoverStrategy(StopLossTakeProfitStrategy):
    def __init__(self, contract, data, ib, params, initial_capital=1_000_000, position_size_pct=0.02,
                 profit_target_pct=0.05, trailing_stop_pct=0.03):
        super().__init__(contract, data, ib, params, initial_capital=initial_capital,
                         profit_target_pct=profit_target_pct, trailing_stop_pct=trailing_stop_pct)

    def generate_signals(self):
        """Generate buy/sell signals based on SMA crossover."""
        self.data['fast_sma'] = self.data['close'].rolling(window=self.params.get('fast_period', 10)).mean()
        self.data['slow_sma'] = self.data['close'].rolling(window=self.params.get('slow_period', 30)).mean()

        # Generate signals: 1 for Buy, -1 for Sell, 0 for Neutral
        self.data['signal'] = 0
        self.data.loc[self.data['fast_sma'] > self.data['slow_sma'], 'signal'] = 1
        self.data.loc[self.data['fast_sma'] < self.data['slow_sma'], 'signal'] = -1
        self.data['position'] = self.data['signal'].shift(1)
        
        return self.data

    def _should_buy(self, i):
        """Custom buy logic for SMA crossover: Buy when fast SMA crosses above slow SMA."""
        return self.data_with_signals['signal'].iloc[i] == 1 and self.data_with_signals['signal'].iloc[i - 1] != 1

    def plot_indicators(self):
        """Plot the SMA lines."""
        plt.plot(self.data_with_signals['fast_sma'], label=f"{self.params.get('fast_period', 10)}-Period SMA", color='orange')
        plt.plot(self.data_with_signals['slow_sma'], label=f"{self.params.get('slow_period', 30)}-Period SMA", color='purple')

class BollingerBandsStrategy(StopLossTakeProfitStrategy):
    def __init__(self, contract, data, ib, params, initial_capital=1_000_000, position_size_pct=0.02,
                 profit_target_pct=0.05, trailing_stop_pct=0.03):
        super().__init__(contract, data, ib, params, initial_capital=initial_capital,
                         profit_target_pct=profit_target_pct, trailing_stop_pct=trailing_stop_pct)

    def generate_signals(self):
        """Generate buy/sell signals based on Bollinger Bands."""
        window = self.params.get('period', 20)
        std_dev = self.params.get('std_dev', 2)

        self.data['sma'] = self.data['close'].rolling(window=window).mean()
        self.data['upper_band'] = self.data['sma'] + std_dev * self.data['close'].rolling(window=window).std()
        self.data['lower_band'] = self.data['sma'] - std_dev * self.data['close'].rolling(window=window).std()

        # Generate signals: 1 for Buy when price crosses above lower band, -1 for Sell when it crosses below upper band
        self.data['signal'] = 0
        self.data.loc[self.data['close'] < self.data['lower_band'], 'signal'] = 1
        self.data.loc[self.data['close'] > self.data['upper_band'], 'signal'] = -1
        self.data['position'] = self.data['signal'].shift(1)
        
        return self.data

    def _should_buy(self, i):
        """Custom buy logic for Bollinger Bands: Buy when close price crosses above lower band."""
        return self.data_with_signals['signal'].iloc[i] == 1 and self.data_with_signals['signal'].iloc[i - 1] != 1

    def plot_indicators(self):
        """Plot Bollinger Bands."""
        plt.plot(self.data_with_signals['sma'], label="SMA", color="purple", linestyle="--")
        plt.plot(self.data_with_signals['upper_band'], label="Upper Band", color="orange", linestyle="--")
        plt.plot(self.data_with_signals['lower_band'], label="Lower Band", color="orange", linestyle="--")


# My concern is that the bollinger bands strategy is not that effective if the stock does not go up.
# I want to create a sideways bollinger bands strategy that will work better in sideways markets.
# sideways_bollinger_bands_strategy.py

class SidewaysBollingerBandsStrategy(StopLossTakeProfitStrategy):

    def __init__(self, contract, data, ib, params, initial_capital=1_000_000, position_size_pct=0.02,
                 profit_target_pct=0.05, trailing_stop_pct=0.03):
        super().__init__(contract, data, ib, params, initial_capital=initial_capital,
                         profit_target_pct=profit_target_pct, trailing_stop_pct=trailing_stop_pct)
        self.rsi_window = self.params.get('rsi_window', 14)

    def generate_signals(self):
        """Generate buy/sell signals based on Bollinger Bands and set stop-loss/take-profit."""
        period = self.params.get('period', 20)
        std_dev = self.params.get('std_dev', 2)
        self.data['sma'] = self.data['close'].rolling(window=period).mean()
        self.data['upper_band'] = self.data['sma'] + std_dev * self.data['close'].rolling(window=period).std()
        self.data['lower_band'] = self.data['sma'] - std_dev * self.data['close'].rolling(window=period).std()

        # calculate rsi
        delta = self.data['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=self.rsi_window).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=self.rsi_window).mean()
        rs = gain / loss
        self.data['rsi'] = 100 - (100 / (1 + rs))

        self.data['signal'] = 0
        self.data.loc[self.data['close'] < self.data['lower_band'], 'signal'] = 1  # Buy at lower band
        self.data.loc[self.data['close'] > self.data['sma'], 'signal'] = -1  # Sell at middle band

        return self.data

    def _should_buy(self, i):
        """Custom buy logic based on Bollinger Bands."""
        return self.data_with_signals['signal'].iloc[i] == 1 and self.data_with_signals['signal'].iloc[i - 1] != 1 and self.data_with_signals['rsi'].iloc[i] < 30