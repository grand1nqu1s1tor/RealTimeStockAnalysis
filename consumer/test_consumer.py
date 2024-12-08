import sys
sys.path.append("/app")

import os
from pyspark.sql import SparkSession
from pyspark.sql.functions import from_json, col, to_timestamp
from pyspark.sql.types import StructType, StructField, StringType, DoubleType, TimestampType
from datetime import datetime
from logs.logger import setup_logger
from InfluxDBWriter import InfluxDBWriter

# Kafka and database configurations
KAFKA_TOPIC_NAME = "real-time-stock-prices"
KAFKA_BOOTSTRAP_SERVERS = "kafka:9092"

# Postgres properties (if needed elsewhere in your pipeline)
postgresql_properties = {
    "user": "admin",
    "password": "admin",
    "driver": "org.postgresql.Driver"
}

# Spark dependencies
scala_version = '2.12'
spark_version = '3.3.3'
packages = [
    f'org.apache.spark:spark-sql-kafka-0-10_{scala_version}:{spark_version}',
    'org.apache.kafka:kafka-clients:2.8.1'
]

# Kafka schema for stock prices
stock_price_schema = StructType([
    StructField("stock", StringType(), True),
    StructField("date", StringType(), True),  # Parse 'date' as StringType
    StructField("open", DoubleType(), True),
    StructField("high", DoubleType(), True),
    StructField("low", DoubleType(), True),
    StructField("close", DoubleType(), True),
    StructField("volume", DoubleType(), True)
])

def process_batch(batch_df, batch_id):
    """
    Process each micro-batch and write data to InfluxDB.
    """
    logger.info(f"Processing batch {batch_id}")

    try:
        # Convert 'date' to UTC timestamp
        parsed_df = batch_df.select(
            col("stock_price.stock").alias("stock"),
            to_timestamp("stock_price.date", "yyyy-MM-dd'T'HH:mm:ssXXX").alias("date"),  # Parse date with timezone
            col("stock_price.open"),
            col("stock_price.high"),
            col("stock_price.low"),
            col("stock_price.close"),
            col("stock_price.volume")
        )

        # Filter out rows with null values in essential fields
        valid_rows = parsed_df.filter(
            "open IS NOT NULL AND high IS NOT NULL AND low IS NOT NULL AND close IS NOT NULL AND volume IS NOT NULL"
        )

        # Write each row to InfluxDB
        for row in valid_rows.collect():
            # Convert timestamp to nanoseconds
            timestamp_ns = int(row["date"].timestamp() * 1e9) if row["date"] else None
            tags = {"stock": row["stock"]}
            fields = {
                "open": row["open"],
                "high": row["high"],
                "low": row["low"],
                "close": row["close"],
                "volume": row["volume"]
            }

            try:
                logger.info(f"Writing to InfluxDB: timestamp={timestamp_ns}, tags={tags}, fields={fields}")
                influxdb_writer.process(timestamp_ns, tags, fields)
            except Exception as e:
                logger.error(f"Failed to write to InfluxDB: {e}")
    except Exception as e:
        logger.error(f"Error processing batch: {e}")


if __name__ == "__main__":
    # Set up logger
    logger = setup_logger(__name__, 'consumer.log')

    # Initialize Spark session
    spark = (
        SparkSession.builder.appName("KafkaInfluxDBStreaming")
        .master("spark://spark-master:7077")
        .config("spark.jars.packages", ",".join(packages))
        .config("spark.executor.extraClassPath", "/app/packages/postgresql-42.2.18.jar")
        .getOrCreate()
    )

    spark.sparkContext.setLogLevel("ERROR")

    # Initialize InfluxDB writer
    influxdb_writer = InfluxDBWriter(
        os.environ.get("INFLUXDB_BUCKET", "stock-prices-bucket"),
        os.environ.get("INFLUXDB_MEASUREMENT", "stock-price-v1")
    )

    # Read data from Kafka
    kafka_stream = (
        spark.readStream.format("kafka")
        .option("kafka.bootstrap.servers", KAFKA_BOOTSTRAP_SERVERS)
        .option("subscribe", KAFKA_TOPIC_NAME)
        .option("startingOffsets", "earliest")
        .load()
    )

    # Debug Kafka schema
    logger.info("Kafka Stream Schema:")
    kafka_stream.printSchema()

    # Parse the Kafka data and apply the stock price schema
    parsed_stream = kafka_stream.select(
        from_json(col("value").cast("string"), stock_price_schema).alias("stock_price")
    )

    # Write to InfluxDB using foreachBatch
    query = (
        parsed_stream.writeStream.foreachBatch(process_batch)
        .outputMode("append")
        .option("checkpointLocation", "/tmp/spark-checkpoint")
        .start()
    )

    logger.info("Streaming job started. Awaiting termination...")
    query.awaitTermination()
