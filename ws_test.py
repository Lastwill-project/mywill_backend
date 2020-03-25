import time
import json
import sys
import pika

connection = pika.BlockingConnection(pika.ConnectionParameters(
        '127.0.0.1',
        5672,
        'ducxwill',
        pika.PlainCredentials('ducxwill', 'ducxwill'),
        heartbeat_interval=0
))

channel = connection.channel()

channel.queue_declare(queue='websockets', durable=True, auto_delete=False, exclusive=False)



channel.basic_publish(
        exchange='',
        routing_key='websockets',
        body=sys.argv[2],
        properties=pika.BasicProperties(expiration='30000', type=sys.argv[1]),
)
print('ok')

connection.close()
