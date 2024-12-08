import sys
# append the path of the parent directory
sys.path.append("./")

import yfinance as yf
import pandas as pd
import numpy as np

import json
from datetime import datetime, timedelta, time, timezone
from dotenv import load_dotenv
import time as t

load_dotenv()

def send_to_kafka(producer, topic, key, partition, message, logger):
    try:
        # print("sent to kafka", message)
        #producer.produce(topic, key=key, partition=partition, value=json.dumps(message).encode("utf-8"))
        #Excluding the partition for testing since we only one partition configured as of now.
        producer.produce(topic, key=key, value=json.dumps(message).encode("utf-8"))
        producer.flush()
    except Exception as e:
        logger.error(f"Failed to produce message to Kafka: {e}")

def retrieve_historical_data(producer, stock_symbol, kafka_topic, logger):
    logger.info("retrieve_historical_data function called")  # Debug log
    stock_symbols = stock_symbol.split(",") if stock_symbol else []
    if not stock_symbols:
        logger.error("No stock symbols provided in the environment variable.")
        return

    # Fetch historical data for each stock
    for stock_symbol in stock_symbols:
        try:
            logger.info(f"Fetching historical data for {stock_symbol}")
            historical_data = yf.Ticker(stock_symbol).history(period="1mo", interval="2m", prepost=True)

            if historical_data.empty:
                logger.error(f"No historical data found for stock: {stock_symbol}")
                continue

            logger.info(f"Retrieved historical data for {stock_symbol}: {historical_data.head()}")

            # Ensure necessary columns exist
            required_columns = ["Open", "High", "Low", "Close", "Volume"]
            missing_columns = [col for col in required_columns if col not in historical_data.columns]
            if missing_columns:
                logger.error(f"Missing columns in historical data for {stock_symbol}: {missing_columns}")
                continue

            # Replace rows where Volume = 0 with NaN
            historical_data.loc[historical_data["Volume"] == 0, required_columns] = np.nan

            # Iterate over each row and send to Kafka
            for index, row in historical_data.iterrows():
                historical_data_point = {
                    'stock': stock_symbol,
                    'date': row.name.isoformat(),
                    'open': row['Open'],
                    'high': row['High'],
                    'low': row['Low'],
                    'close': row['Close'],
                    'volume': row['Volume']
                }

                logger.info(f"Sending data to Kafka: {historical_data_point}")
                send_to_kafka(producer, kafka_topic, stock_symbol, 0, historical_data_point, logger)

            logger.info(f"Successfully sent historical data for {stock_symbol} to Kafka topic {kafka_topic}")

        except Exception as e:
            logger.exception(f"Error retrieving or sending historical data for {stock_symbol}: {e}")


def retrieve_real_time_data(producer, stock_symbol, kafka_topic, logger):
    stock_symbols = stock_symbol.split(",") if stock_symbol else []
    if not stock_symbols:
        logger.error("No stock symbols provided in the environment variable.")
        exit(1)

    while True:
        current_time = datetime.now()
        is_market_open_bool = is_stock_market_open(current_time)
        if is_market_open_bool:
            end_time = datetime.now()
            start_time = end_time - timedelta(days=1)

            for symbol_index, sym in enumerate(stock_symbols):
                real_time_data = yf.download(sym, start=start_time, end=end_time, interval="2m")
                real_time_data.columns = [c[0] for c in real_time_data.columns]
                print(real_time_data.columns)



                if not real_time_data.empty:
                    latest_data_point = real_time_data.iloc[-1]
                    print(latest_data_point)
                    # Convert values to Python native types
                    date_str = latest_data_point.name.isoformat() if hasattr(latest_data_point.name, 'isoformat') else str(latest_data_point.name)
                    open_val = float(latest_data_point['Open']) if not pd.isnull(latest_data_point['Open']) else None
                    high_val = float(latest_data_point['High']) if not pd.isnull(latest_data_point['High']) else None
                    low_val = float(latest_data_point['Low']) if not pd.isnull(latest_data_point['Low']) else None
                    close_val = float(latest_data_point['Close']) if not pd.isnull(latest_data_point['Close']) else None
                    volume_val = float(latest_data_point['Volume']) if not pd.isnull(latest_data_point['Volume']) else None

                    real_time_data_point = {
                        'stock': str(sym),
                        'date': date_str,
                        'open': open_val,
                        'high': high_val,
                        'low': low_val,
                        'close': close_val,
                        'volume': volume_val
                    }

                    send_to_kafka(producer, kafka_topic, sym, symbol_index, real_time_data_point, logger)
                    logger.info(f"Stock value retrieved and pushed to kafka topic {kafka_topic}")
        else:
            # Market closed scenario
            for symbol_index, sym in enumerate(stock_symbols):
                null_data_point = {
                    'stock': sym,
                    'date': current_time.isoformat(),
                    'open': None,
                    'high': None,
                    'low': None,
                    'close': None,
                    'volume': None
                }
                send_to_kafka(producer, kafka_topic, sym, symbol_index, null_data_point, logger)
        t.sleep(3)

def get_stock_details(stock_symbol, logger):
    stock_symbols = stock_symbol.split(",") if stock_symbol else []
    print(stock_symbols)
    logger.info(stock_symbols)
    if not stock_symbols:
        logger.error(f"No stock symbols provided in the environment variable.")
        exit(1)
    # Create a Ticker object for the specified stock symbol
    stock_details = []
    for stock_symbol in stock_symbols:
        try:
            # Create a Ticker object for the specified stock symbol
            ticker = yf.Ticker(stock_symbol)

            # Retrieve general stock information
            stock_info = {
                'Date': datetime.now().strftime('%Y-%m-%d'),
                'Symbol': stock_symbol,
                'ShortName': ticker.info['shortName'],
                'LongName': ticker.info['longName'],
                'Industry': ticker.info['industry'],
                'Sector': ticker.info['sector'],
                'MarketCap': ticker.info['marketCap'],
                'ForwardPE': ticker.info['forwardPE'],
                'TrailingPE': ticker.info['trailingPE'],
                'Currency': ticker.info['currency'],
                'FiftyTwoWeekHigh': ticker.info['fiftyTwoWeekHigh'],
                'FiftyTwoWeekLow': ticker.info['fiftyTwoWeekLow'],
                'FiftyDayAverage': ticker.info['fiftyDayAverage'],
                'Exchange': ticker.info['exchange'],
                'ShortRatio': ticker.info['shortRatio']
            }
            stock_details.append(stock_info)
        except Exception as e:
            logger.info(f"Error fetching stock details for {stock_symbol}: {str(e)}")

    return stock_details

def is_stock_market_open(current_datetime=None):
    # If no datetime is provided, use the current datetime
    if current_datetime is None:
        current_datetime = datetime.now()

    # Define NYSE trading hours in Eastern Time Zone
    market_open_time = time(9, 30)
    market_close_time = time(16, 0)

    # Convert current_datetime to Eastern Time Zone
    current_time_et = current_datetime.astimezone(timezone(timedelta(hours=-4)))  # EDT (UTC-4)

    # Check if it's a weekday and within trading hours
    if current_time_et.weekday() < 5 and market_open_time <= current_time_et.time() < market_close_time:
        return True
    else:
        return False