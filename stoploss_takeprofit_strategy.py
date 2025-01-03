# stop_loss_take_profit_strategy.py
# stop_loss_take_profit_strategy.py
import matplotlib.pyplot as plt
from base_strategy import BaseStrategy
import logging
import os
import numpy as np
from ib_insync import MarketOrder
import pandas as pd
import datetime


class StopLossTakeProfitStrategy(BaseStrategy):
    def __init__(self, stock, data, ib, params=None, initial_capital=1_000_000, position_size_pct=0.02, profit_target_pct=0.05, trailing_stop_pct=0.03):
        super().__init__(stock, data, ib, params, initial_capital, position_size_pct)
        self.profit_target_pct = profit_target_pct
        self.contract = stock
        self.trailing_stop_pct = trailing_stop_pct
        self.current_position = 0
        self.current_balance = self.initial_capital
        self.avg_entry_price = 0
        self.entry_date = None
        self.highest_price_since_entry = 0
        # set lowest price to infty
        self.lowest_price_since_entry = float('inf')
        self.logger = None
        self._setup_logger()

    def log_statistics_and_trades(self, statistics):
        # Prepare statistics string

        stats_str = f"Final statistics"
        for key, value in statistics.items():
            stats_str += f"{key}: {value}, " + "\n"
        stats_str += "\n\n"

        # Log statistics to the head of the log file
        with open(self.logger.handlers[0].baseFilename, 'r+') as file:
            content = file.read()
            file.seek(0, 0)
            file.write(stats_str + content)


    def trade_statistics(self):
        if not self.trades and self.current_position == 0:
            # No trades and no open position
            print("No trades were recorded.")
            # write to log file
            self.logger.info(f"No trades were recorded.")
            return {
                'total_trades': 0,
                'winning_trades': 0,
                'losing_trades': 0,
                'average_return': None,
                'average_duration': None,
                'final_balance': self.current_balance,
                'final_portfolio_value': self.final_portfolio_value
            }
        
        # Convert trades to DataFrame if trades were recorded
        df_trades = pd.DataFrame(self.trades) if self.trades else pd.DataFrame(columns=['return', 'duration'])
        
        # Check for open position at the end of the backtest
        if self.current_position > 0:
            final_price = self.data_with_signals['close'].iloc[-1]
            unrealized_return = (final_price - self.avg_entry_price) / self.avg_entry_price
            unrealized_duration = (self.data_with_signals.index[-1] - self.entry_date).total_seconds() / 60  # Duration in minutes
            
            # Add hypothetical trade to the DataFrame
            df_trades = pd.concat([df_trades, pd.DataFrame([{
                'entry_date': self.entry_date,
                'exit_date': self.data_with_signals.index[-1],
                'entry_price': self.avg_entry_price,
                'exit_price': final_price,
                'shares': self.current_position,
                'return': unrealized_return,
                'profit': unrealized_return * self.avg_entry_price * self.current_position,
                'duration': unrealized_duration
            }])], ignore_index=True)
            
            print(f"Holding {self.current_position} shares as an open position at the end with unrealized return: {unrealized_return}, Duration: {unrealized_duration} minutes")
            # write to log file
            self.logger.info(f"Holding {self.current_position} shares as an open position at the end with unrealized return: {unrealized_return}, Duration: {unrealized_duration} minutes")
        
        # Force columns to numeric for calculations
        df_trades['return'] = pd.to_numeric(df_trades['return'], errors='coerce')
        df_trades['duration'] = pd.to_numeric(df_trades['duration'], errors='coerce')
        
        def calculate_sharpe(df_trades):
            """
            Calculate the Sharpe Ratio from trade returns, assuming duration is in minutes.
            """
            # Filter out trades with very short durations (e.g., <1 minute) to avoid division by very small numbers
            df_trades = df_trades[df_trades['duration'] > 1]

            # Calculate daily returns, making sure 'duration' is in minutes
            df_trades['daily_return'] = df_trades['return'] / (df_trades['duration'] / (60 * 24))
            daily_returns = df_trades['daily_return']

            # Debugging: Print mean and standard deviation of daily returns
            print(f"Mean daily return: {daily_returns.mean()}")
            print(f"Standard deviation of daily returns: {daily_returns.std()}")

            # Calculate Sharpe Ratio, using np.sqrt(252) to annualize
            if daily_returns.std() != 0:
                sharpe_ratio = np.sqrt(252) * daily_returns.mean() / daily_returns.std()
            else:
                print("Standard deviation of daily returns is zero, setting Sharpe Ratio to 0.")
                sharpe_ratio = 0  # Avoid division by zero if standard deviation is zero

            return sharpe_ratio


        self.sharpe_ratio = calculate_sharpe(df_trades)
        # Calculate trade statistics
        stats = {
            'Stock': self.stock.symbol,
            'total_trades': len(df_trades),
            'winning_trades': df_trades[df_trades['return'] > 0].shape[0],
            'losing_trades': df_trades[df_trades['return'] <= 0].shape[0],
            'average_return': df_trades['return'].mean(),
            'average_duration': df_trades['duration'].mean(),
            'final_balance': self.current_balance,
            'final_portfolio_value': self.final_portfolio_value,
            'sharpe_ratio': self.sharpe_ratio
        }

        self.log_statistics_and_trades(stats)
        return stats
    # existing methods like _execute_trades, _should_buy, etc.
    def _should_buy(self, i):
        return self.data_with_signals['signal'].iloc[i] == 1 

    def _should_sell(self, i):
        return self.data_with_signals['signal'].iloc[i] == -1 

    def plot_trades(self, filename=None):
        """Plot close price with indicators, buy signals, profit-taking, and stop-loss exits."""
        fig, ax = plt.subplots(figsize=(14, 7))
        ax.plot(self.data_with_signals['close'], label='Close Price', color='blue')
        self.plot_indicators() 

        ax2 = ax.twinx()
        ax2.bar(self.data_with_signals.index, self.data_with_signals['volume'], alpha=0.3, color='gray', label='Volume', width=0.5)
        ax2.set_ylabel('Volume')

        # Identify Buy signals
        # use the _should_buy rule to get the buy signals

        # Initialize lists to collect buy/sell data
        buy_dates = []
        buy_prices = []
        sell_dates = []
        sell_prices = []

        # Iterate over the rows to apply the _should_buy and _should_sell conditions
        for i in range(len(self.data_with_signals)):
            if self._should_buy(i):
                buy_dates.append(self.data_with_signals.index[i])  # Record the index (date)
                buy_prices.append(self.data_with_signals['close'].iloc[i])  # Record the close price

            if self._should_sell(i):
                sell_dates.append(self.data_with_signals.index[i])  # Record the index (date)
                sell_prices.append(self.data_with_signals['close'].iloc[i])  # Record the close price


        # Identify Profit-Taking Exits
        profit_exits = self.data_with_signals[self.data_with_signals['profit_take']]
        profit_dates = profit_exits.index
        profit_prices = profit_exits['close']

        # Identify Stop-Loss Exits
        stop_exits = self.data_with_signals[self.data_with_signals['stop_loss']]
        stop_dates = stop_exits.index
        stop_prices = stop_exits['close']

        # Plot Buy Signals
        if buy_dates:
            ax.plot(buy_dates, buy_prices, '^', markersize=10, color='green', label='Buy Signal')

        # Plot Profit-Taking Exits
        if not profit_dates.empty:
            ax.plot(profit_dates, profit_prices, 'o', markersize=8, color='gold', label='Profit-Take Exit')

        # Plot Stop-Loss Exits
        if not stop_dates.empty:
            ax.plot(stop_dates, stop_prices, 'x', markersize=8, color='red', label='Stop-Loss Exit')

        if sell_dates:
            ax.plot(sell_dates, sell_prices, 'v', markersize=10, color='black', label='Sell Signal')

        # Add title, legend, and labels
        param_str = "_".join([f"{k}{v}" for k, v in self.params.items()])
        # Add profit target and stop loss to title
        param_str += f"_PT{self.profit_target_pct}_SL{self.trailing_stop_pct}"
        plt.title(f"{self.stock.symbol} - {self.__class__.__name__} Strategy ({param_str})")
        plt.xlabel('Date')
        plt.ylabel('Price')
        ax.legend()
        ax2.legend()

        # Set dynamic filename based on final portfolio value
        final_value_str = f"{self.final_portfolio_value:.2f}" if self.final_portfolio_value is not None else "NA"
        filename = filename or f"output/{final_value_str}_{self.stock.symbol}_{self.__class__.__name__}_{param_str}.png"

        # Save plot to file
        plt.savefig(filename)
        plt.close()

    def plot_indicators(self):
        """Override in subclasses to plot strategy-specific indicators."""
        pass


    def _execute_trades(self):
        """Manage entries and exits with stop-loss and take-profit logic."""
        self.data_with_signals['profit_take'] = False
        self.data_with_signals['stop_loss'] = False

        halted_trading_day = None

        for i in range(1, len(self.data_with_signals)):
            current_price = self.data_with_signals['close'].iloc[i]
            portfolio_value = self.current_balance + (self.current_position * current_price)
            self.portfolio_values.append({'date': self.data_with_signals.index[i], 'portfolio_value': portfolio_value})

            if halted_trading_day == self.data_with_signals.index[i].date():
                continue
            if self.current_position == 0:
                if self._should_buy(i):
                    self._buy_position(current_price, i)
                elif self._should_sell(i):
                    self._sell_position_short(current_price, i)
            elif self.current_position > 0:
                if self._hit_profit_target(current_price):
                    self._sell_position(current_price, i, 'profit_take')
                elif self._hit_trailing_stop(current_price):
                    self._sell_position(current_price, i, 'stop_loss')
                    # stop losses come with a 1 day cooldown
                    # no more trades can be made on the same day
                    halted_trading_day = self.data_with_signals.index[i].date()

                elif self._should_buy(i):
                    self._buy_position(current_price, i)
                elif self._should_sell(i):
                    self._sell_position(current_price, i, 'signal')
            elif self.current_position < 0:
                if self._hit_profit_target_short(current_price):
                    self._buy_position_short(current_price, i, 'profit_take')
                elif self._hit_trailing_stop_short(current_price):
                    self._buy_position_short(current_price, i, 'stop_loss')
                    # stop losses come with a 1 day cooldown
                    # no more trades can be made on the same day
                    halted_trading_day = self.data_with_signals.index[i].date()
                elif self._should_sell(i):
                    self._sell_position_short(current_price, i)
                elif self._should_buy(i):
                    self._buy_position_short(current_price, i, 'signal')


            # Update highest price since entry if holding position
            if self.current_position > 0:
                self.highest_price_since_entry = max(self.highest_price_since_entry, current_price)
            elif self.current_position < 0:
                self.lowest_price_since_entry = min(self.lowest_price_since_entry, current_price)
                

        # Final portfolio value calculation if still holding shares, skip if no trades executed
        if self.current_position > 0:
            self.final_portfolio_value = self.current_balance + (self.current_position * self.data_with_signals['close'].iloc[-1])
        else:
            self.final_portfolio_value = self.current_balance

    def _buy_position(self, current_price, index):
        """Execute a buy operation."""
        shares_to_buy = (self.current_balance * self.position_size_pct) // current_price
        buy_cost = shares_to_buy * current_price
        if shares_to_buy > 0 and buy_cost <= self.current_balance:
            self.avg_entry_price = ((self.avg_entry_price * self.current_position) + (current_price * shares_to_buy)) / (self.current_position + shares_to_buy)
            self.current_balance -= buy_cost
            self.entry_date = self.data_with_signals.index[index] if self.current_position == 0 else self.entry_date
            self.current_position += shares_to_buy
            self.highest_price_since_entry = max(self.highest_price_since_entry, current_price)
            self.logger.info(f"Long Buy {shares_to_buy:.2f} shares at {current_price} on {self.data_with_signals.index[index]}")

    def _sell_position(self, current_price, index, exit_type):
        """Helper method to execute a sell operation and log the type of exit."""
        sell_revenue = self.current_position * current_price
        profit = (current_price - self.avg_entry_price) * self.current_position
        
        # Check if entry_date is not None before calculating duration
        if self.entry_date is not None:
            duration_minutes = (self.data_with_signals.index[index] - self.entry_date).total_seconds() / 60
        else:
            # Handle case when entry_date is None
            duration_minutes = 0  # Default to 0 or any other default duration you prefer
            self.logger.warning("Warning: entry_date is None when calculating duration in _sell_position.")
        
        self.current_balance += sell_revenue
        self.trades.append({
            'entry_date': self.entry_date,
            'exit_date': self.data_with_signals.index[index],
            'entry_price': self.avg_entry_price,
            'exit_price': current_price,
            'shares': self.current_position,
            'return': profit / (self.avg_entry_price * self.current_position),
            'profit': profit,
            'duration': duration_minutes
        })
        self.data_with_signals.at[self.data_with_signals.index[index], exit_type] = True
        self.logger.info(f"Sell to close {self.current_position:.2f} shares at {current_price} on {self.data_with_signals.index[index]} (Exit: {exit_type.capitalize()}, Profit: {profit}, Duration: {duration_minutes} minutes)")
        
        # Reset position attributes
        self.current_position = 0
        self.avg_entry_price = 0
        self.entry_date = None
        self.highest_price_since_entry = 0

    def _sell_position_short(self, current_price, index):
        """Helper method to execute a sell operation and log the type of exit."""
        without_margin = self.current_balance + (self.current_position * current_price)
        shares_to_sell = (without_margin * self.position_size_pct) // current_price
        sell_revenue = shares_to_sell * current_price
        if shares_to_sell > 0:
            self.avg_entry_price = ((self.avg_entry_price * abs(self.current_position)) + (current_price * shares_to_sell)) / (abs(self.current_position) + shares_to_sell)
            self.current_balance += sell_revenue
            self.entry_date = self.data_with_signals.index[index] if self.current_position == 0 else self.entry_date
            self.current_position -= shares_to_sell
            # update the lowest price since entry as the minimum of the current price and the lowest price since entry
            self.lowest_price_since_entry = min(self.lowest_price_since_entry, current_price)
            self.logger.info(f"Short Sell {shares_to_sell:.2f} shares at {current_price} on {self.data_with_signals.index[index]}")

    def _buy_position_short(self, current_price, index,exit_type):
        """Execute a buy to cover operation."""
        buy_cost = abs(self.current_position) * current_price
        profit = (self.avg_entry_price - current_price) * abs(self.current_position)
        if self.entry_date is not None:
            duration_minutes = (self.data_with_signals.index[index] - self.entry_date).total_seconds() / 60
        else:
            # Handle case when entry_date is None
            duration_minutes = 0  # Default to 0 or any other default duration you prefer
            self.logger.warning("Warning: entry_date is None when calculating duration in _sell_position.")
        
        self.current_balance -= buy_cost
        self.trades.append({
            'entry_date': self.entry_date,
            'exit_date': self.data_with_signals.index[index],
            'entry_price': self.avg_entry_price,
            'exit_price': current_price,
            'shares': abs(self.current_position),
            'return': profit / (self.avg_entry_price * abs(self.current_position)),
            'profit': profit,
            'duration': duration_minutes
        })
        self.data_with_signals.at[self.data_with_signals.index[index], exit_type] = True
        self.logger.info(f"Buy to cover {self.current_position:.2f} shares at {current_price} on {self.data_with_signals.index[index]} (Exit: {exit_type.capitalize()}, Profit: {profit}, Duration: {duration_minutes} minutes)")
        
        # Reset position attributes
        self.current_position = 0
        self.avg_entry_price = 0
        self.entry_date = None
        self.lowest_price_since_entry = float('inf')



    def paper_trade_buy_long(self, current_price):
        shares_to_buy = (self.current_balance * self.position_size_pct) // current_price
        buy_cost = shares_to_buy * current_price
        if shares_to_buy > 0 and buy_cost <= self.current_balance:
            self.avg_entry_price = ((self.avg_entry_price * self.current_position) + (current_price * shares_to_buy)) / (self.current_position + shares_to_buy)
            self.current_balance -= buy_cost
            self.current_position += shares_to_buy
            self.entry_date = self.data_with_signals.index[-1]
            self.highest_price_since_entry = current_price
            # Above was the internal, now we place the order
            order = MarketOrder('BUY', shares_to_buy)
            trade = self.ib.placeOrder(self.contract, order)
            self.logger.info(f"Paper trade LONG BUY order for {shares_to_buy:.2f} shares at {current_price} placed.")
            # log the current value of the portfolio
            self.logger.info(f"Current portfolio value: {self.current_balance + self.current_position * current_price}")
            return trade
        self.logger.warning("Insufficient balance for buy order.")
        return None

    # Paper trading method to place a live sell order
    def paper_trade_sell_close(self, current_price, exit_type):
        if self.current_position > 0:
            sell_revenue = self.current_position * current_price
            profit = (current_price - self.avg_entry_price) * self.current_position
            if self.entry_date is not None:
                duration_minutes = (self.data_with_signals.index[-1] - self.entry_date).total_seconds() / 60
            else:
                # Handle case when entry_date is None
                duration_minutes = 0  # Default to 0 or any other default duration you prefer
                self.logger.warning("Warning: entry_date is None when calculating duration in _sell_position.")

            self.current_balance += sell_revenue
            self.trades.append({
                'entry_date': self.entry_date,
                'exit_date': self.data_with_signals.index[-1],
                'entry_price': self.avg_entry_price,
                'exit_price': current_price,
                'shares': self.current_position,
                'return': profit / (self.avg_entry_price * self.current_position),
                'profit': profit,
                'duration': duration_minutes
            })
            self.data_with_signals.at[self.data_with_signals.index[-1], exit_type] = True
            # Above was the internal, now we place the order
            order = MarketOrder('SELL', self.current_position)
            trade = self.ib.placeOrder(self.contract, order)
            self.logger.info(f"Paper trade SELL order for {self.current_position:.2f} shares at {current_price} placed." + exit_type)
            # log the current value of the portfolio
            self.logger.info(f"Current portfolio value: {self.current_balance}")
            self.current_position = 0
            self.avg_entry_price = 0
            self.entry_date = None
            self.highest_price_since_entry = 0

            return trade
        self.logger.warning("No position to sell.")
        return None
    
    def paper_trade_sell_short(self, current_price):
        pass

    def paper_trade_buy_cover(self, current_price, exit_type):
        pass

    def _hit_profit_target(self, current_price):
        """Check if the profit target is met."""
        if self.avg_entry_price == 0:
            return False
        return (current_price - self.avg_entry_price) / self.avg_entry_price >= self.profit_target_pct

    def _hit_trailing_stop(self, current_price):
        """Check if the trailing stop is met."""
        if self.highest_price_since_entry == 0:
            return False
        return (self.highest_price_since_entry - current_price) / self.highest_price_since_entry >= self.trailing_stop_pct
    
    def _hit_profit_target_short(self, current_price):
        """Check if the profit target is met."""
        if self.avg_entry_price == 0:
            return False
        return (self.avg_entry_price - current_price) / self.avg_entry_price >= self.profit_target_pct
    
    def _hit_trailing_stop_short(self, current_price):
        """Check if the trailing stop is met."""
        if self.lowest_price_since_entry == float('inf'):
            return False
        return (current_price - self.lowest_price_since_entry) / self.lowest_price_since_entry >= self.trailing_stop_pct
    
    def _setup_logger(self):
        """Sets up a logger for the strategy instance that overwrites on each run."""
        # if no output directory exists, create it
        if not os.path.exists('output'):
            os.makedirs('output')
        # Format the hyperparameters for file naming
        hyperparam_str = "_".join([f"{k}{v}" for k, v in self.params.items()])
        hyperparam_str += f"_PT{self.profit_target_pct}_SL{self.trailing_stop_pct}"

        date = self.data.index[-1].strftime("%Y-%m-%d")

        log_filename = os.path.join("output", f"{self.stock.symbol}_{date}_{self.__class__.__name__}_{hyperparam_str}.log")

        self.logger = logging.getLogger(f"{self.stock.symbol}_{date}_{self.__class__.__name__}_{hyperparam_str}")

        # Clear existing handlers to avoid duplicate logging
        if self.logger.hasHandlers():
            self.logger.handlers.clear()

        # Create file handler in overwrite mode
        file_handler = logging.FileHandler(log_filename, mode='w')
        formatter = logging.Formatter('%(asctime)s - %(message)s')
        file_handler.setFormatter(formatter)
        self.logger.addHandler(file_handler)
        self.logger.setLevel(logging.INFO)

        # Log the starting conditions
        self.logger.info(f"Starting {self.__class__.__name__} with initial capital: {self.initial_capital}")
        self.logger.info(f"Hyperparameters: {self.params}")

    def run_paper_trading(self):
        """Run paper trading by checking signals and placing orders."""
        latest_price = self.data['close'].iloc[-1]

        # Check buy signal and place paper trade if signal changes to 1
        # Check sell signal and place paper trade if signal changes to -1
        if self.current_position == 0:
            if self._should_buy(-1):
                self.paper_trade_buy_long(latest_price)
            elif self._should_sell(-1):
                self.paper_trade_sell_close(latest_price, 'signal')
        elif self.current_position > 0:
            if self._should_buy(-1):
                self.paper_trade_buy_long(latest_price)
            if self._should_sell(-1):
                self.paper_trade_sell_close(latest_price, 'signal')
            elif self._hit_profit_target(latest_price):
                self.paper_trade_sell_close(latest_price, 'profit_take')
            elif self._hit_trailing_stop(latest_price):
                self.paper_trade_sell_close(latest_price, 'stop_loss')

        elif self.current_position < 0:
            if self._should_sell(-1):
                self.paper_trade_sell_short(latest_price, 'signal')
            if self._should_buy(-1):
                self.paper_trade_buy_cover(latest_price, 'signal')
            elif self._hit_profit_target_short(latest_price):
                self.paper_trade_buy_cover(latest_price, 'profit_take')
            elif self._hit_trailing_stop_short(latest_price):
                self.paper_trade_buy_cover(latest_price, 'stop_loss')

        if self.current_position > 0:
            self.highest_price_since_entry = max(self.highest_price_since_entry, latest_price)
        elif self.current_position < 0:
            self.lowest_price_since_entry = min(self.lowest_price_since_entry, latest_price)

    # support second-by-second updates
    def update_with_price(self, current_price, current_time):
        """Update strategy with a single price point and check for signals."""
        
        # Append the new price to the existing data (in-memory)
        latest_data = pd.DataFrame({
            'date': [current_time],
            'close': [current_price]
        }).set_index('date')
        
        # Concatenate the new price to the main data (dropping duplicates)
        self.data = pd.concat([self.data, latest_data]).drop_duplicates(keep='last')

        # Generate signals based on updated data
        self.data_with_signals = self.generate_signals()

        # Run paper trading based on the latest signals
        self.run_paper_trading()