import telegram
import os
import requests
import time
import logging
import sys
from http import HTTPStatus
from exceptions import MessageError, AnswerError, ParseError, StatusCodeError
from dotenv import load_dotenv, find_dotenv


load_dotenv(find_dotenv())


PRACTICUM_TOKEN = os.getenv('PRACTICUM_TOKEN')
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

RETRY_PERIOD = 600
ENDPOINT = 'https://practicum.yandex.ru/api/user_api/homework_statuses/'
HEADERS = {'Authorization': f'OAuth {PRACTICUM_TOKEN}'}


HOMEWORK_VERDICTS = {
    'approved': 'Работа проверена: ревьюеру всё понравилось. Ура!',
    'reviewing': 'Работа взята на проверку ревьюером.',
    'rejected': 'Работа проверена: у ревьюера есть замечания.'
}

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
filehandler = logging.FileHandler('hw_bot.log', mode='w')
streamhandler = logging.StreamHandler(stream=sys.stdout)
formatter = logging.Formatter(
    '%(asctime)s, %(levelname)s, %(message)s, %(name)s, %(funcName)s'
)
streamhandler.setFormatter(formatter)
filehandler.setFormatter(formatter)
logger.addHandler(streamhandler)
logger.addHandler(filehandler)


def check_tokens():
    """Проверка доступности переменных окружения."""
    return all([
        PRACTICUM_TOKEN,
        TELEGRAM_TOKEN,
        TELEGRAM_CHAT_ID,
        ENDPOINT
    ])


def send_message(bot, message):
    """Отправка сообщения в Telegram чат."""
    try:
        logger.debug('Попытка отправить сообщение')
        bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message)
    except Exception as error:
        logger.error(f'Cбой при отправке сообщения в Telegram - {error}')
        raise MessageError(f'Ошибка отправки сообщения - {error}')
    else:
        logger.debug('Сообщение отправленно в telegram')


def get_api_answer(timestamp):
    """Запрос к единственному эндпоинту."""
    new_timestamp = timestamp or int(time.time())
    request_parameters = {
        'url': ENDPOINT,
        'headers': HEADERS,
        'params': {'from_date': new_timestamp},
    }
    try:
        logger.info('Отправка запроса API '
                    'url = {url}, '
                    'время {params}'.format(**request_parameters)
                    )
        response = requests.get(**request_parameters)
        if response.status_code != HTTPStatus.OK:
            raise StatusCodeError('Недоступен API '
                                  'по параметрам url = {url}, '
                                  'headers = {headers}, '
                                  'params = {params}'
                                  .format(**request_parameters)
                                  )
        logger.info(f'Получен ответ от API с кодом {response.status_code}')
        return response.json()
    except Exception as error:
        logger.error(
            'Ошибка при запросе к API '
            'по параметрам url = {url}, '
            'headers = {headers}, '
            'params = {params}'.format(**request_parameters)
        )
        raise AnswerError('Ошибка при запросе к API', error)


def check_response(response):
    """Проверка ответа API на соответствие документации."""
    logger.info('Попытка проверить ответ API')
    if not isinstance(response, dict):
        raise TypeError('Ответ API не является словарем')
    if 'homeworks' not in response or 'current_date' not in response:
        raise KeyError
    homeworks = response.get('homeworks')
    if not isinstance(homeworks, list):
        raise TypeError('Homeworks не является списком')
    logger.info('Ответ API успешно проверен')
    return homeworks


def parse_status(homework):
    """Извлекаем статус работы."""
    logger.info('Попытка извлечь статус домашней работы')
    if 'homework_name' not in homework:
        raise ParseError('В ответе API домашки нет ключа homework_name')
    homework_name = homework.get('homework_name')
    sprint_name = homework.get('lesson_name')
    homework_status = homework.get('status')
    if homework_status not in HOMEWORK_VERDICTS:
        logger.error(f'Неожиданный статус домашней работы - '
                     f'{homework_status}, в ответе API'
                     )
        raise ParseError(
            'API возвращает недокументированный статус домашней работы'
        )
    verdict = HOMEWORK_VERDICTS[homework_status]
    logger.info('Получен статус домашней работы')
    return (f'Изменился статус проверки работы "{homework_name}"'
            f' ({sprint_name}). {verdict}'
            )


def main():
    """Основная логика работы бота."""
    if not check_tokens():
        notification = 'Отсутствуют переменные окружения'
        logger.critical(notification)
        sys.exit(notification)
    bot = telegram.Bot(token=TELEGRAM_TOKEN)
    timestamp = int(time.time())
    previous_message = ''
    while True:
        try:
            response = get_api_answer(timestamp)
            timestamp = response.get('current_data', int(time.time()))
            homework = check_response(response)
            if homework:
                message = parse_status(homework[0])
            else:
                message = 'Новых статусов у домашних работ нет'
            if message != previous_message:
                send_message(bot, message)
                previous_message = message
            else:
                logger.debug(message)
        except Exception as error:
            message = f'Сбой в работе программы: {error}'
            logger.error(message, exc_info=True)
            if message != previous_message:
                send_message(bot, message)
                previous_message = message
        finally:
            time.sleep(RETRY_PERIOD)


if __name__ == '__main__':
    main()
