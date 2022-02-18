import time
import constants
from iiko_lib import *
from loguru import logger
from datetime import date, timedelta

LOGIN = constants.LOGIN
PASSWORD = constants.PASSWORD
TERMINAL_ID = constants.TERMINAL_ID
ORG_ID = constants.ORG_ID
SALEBOT_TOKEN = constants.SALEBOT_TOKEN
SPECIAL_BLOCK_UNSUBSCRIBE = '3126925'
SPECIAL_BLOCK_FEEDBACK_BAMBOOK = '3192632'
SPECIAL_BLOCK_FEEDBACK_CHICKEN = '4951179'
SPECIAL_BLOCK_FEEDBACK_BRUSKETTA = '4951176'
IS_TEST = False


def working_with_cooking(cooking_now, cooking_file, writen_filename):
    """проверяем все достакви что получили статус готовится и отправляем им whatsapp сообщение"""
    # new_delivery = False
    for cookd in cooking_now:
        item = {}
        if not is_send_wa(cookd, cooking_file):  # есть ли данная доставка в списке доставок по которым было
            # отправлено сообщение
            item['id'] = cookd['number']
            item['name'] = cookd['name']
            phone = cookd['phone']
            if check_whatsapp(SALEBOT_TOKEN, phone):  # проверяем наличение на номере вотсап
                item['wa'] = 'YES'
                client_id = get_id_client_by_whatsapp(SALEBOT_TOKEN, phone)
                if client_id == 'NO':  # найден ли клиент в базе SALEBOT по номеру
                    client_id = create_client_in_salebot(SALEBOT_TOKEN, phone)
                    if client_id != 'NO':
                        variables = {
                            # 'name': phone,
                            'Имя': item['name'],
                            'is_guessed': 2,
                            'is_send_unsubscribe_message': 1
                        }
                        write_variables_by_id_salebot(SALEBOT_TOKEN, client_id, variables)
                        send_whatsapp_cooking(SALEBOT_TOKEN, cookd, IS_TEST)
                        migrate_to_special_block(SALEBOT_TOKEN, phone, SPECIAL_BLOCK_UNSUBSCRIBE, IS_TEST)
                else:
                    client_variables = get_variables_by_id_salebot(SALEBOT_TOKEN, client_id)
                    is_unsubscribe = client_variables.get('is_send_unsubscribe_message')
                    variables = {
                        'is_guessed': 2,
                        'Имя': item['name']
                    }
                    if not is_unsubscribe:
                        variables['is_send_unsubscribe_message'] = 1
                    write_variables_by_id_salebot(SALEBOT_TOKEN, client_id, variables)
                    send_whatsapp_cooking(SALEBOT_TOKEN, cookd, IS_TEST)
                    if not is_unsubscribe:
                        migrate_to_special_block(SALEBOT_TOKEN, phone, SPECIAL_BLOCK_UNSUBSCRIBE, IS_TEST)
            else:
                item['wa'] = 'NO'
            # new_delivery = True
            cooking_file.append(item.copy())
    with open(writen_filename, 'w') as outfile:
        json.dump(cooking_file, outfile, indent=4, ensure_ascii=False)
    # if not new_delivery:
    #     logger.info('Нет новых доставок в статусе "Готоаится".')


def working_with_closed(closed_deliveries, closed_wa_file, writen_filename):
    """Проверяются все доставки со статусом закрыта и отправляются сообщения"""
    for delivery in closed_deliveries:
        item = {}
        if not is_send_wa(delivery, closed_wa_file, status='Закрыта'):
            delivery_closed_time = datetime.strptime(delivery.get('closeTime'), '%Y-%m-%d %H:%M:%S')
            now = datetime.strptime(str(datetime.now().replace(microsecond=0)), '%Y-%m-%d %H:%M:%S')
            time_between = int((now - delivery_closed_time).seconds / 60)
            if time_between > 45:
                item['id'] = delivery['number']
                item['name'] = delivery['name']
                logger.info(f'Доставка №{item["id"]} доставлена {time_between} минут назад. Отправляем сообщение')
                phone = delivery['phone']
                if check_whatsapp(SALEBOT_TOKEN, phone):
                    item['wa'] = 'YES'
                    client_id = get_id_client_by_whatsapp(SALEBOT_TOKEN, phone)
                    if client_id != 'NO':
                        marketing = delivery['marketing']
                        if marketing == 'Брускетта':
                            migrate_to_special_block(SALEBOT_TOKEN, phone, SPECIAL_BLOCK_FEEDBACK_BRUSKETTA, IS_TEST)
                        elif marketing == 'ЧикенАзия':
                            migrate_to_special_block(SALEBOT_TOKEN, phone, SPECIAL_BLOCK_FEEDBACK_CHICKEN, IS_TEST)
                        else:
                            migrate_to_special_block(SALEBOT_TOKEN, phone, SPECIAL_BLOCK_FEEDBACK_BAMBOOK, IS_TEST)
                else:
                    item['wa'] = 'NO'
                closed_wa_file.append(item.copy())
    with open(writen_filename, 'w') as outfile:
        json.dump(closed_wa_file, outfile, indent=4, ensure_ascii=False)


def today_at(hr, min=0, sec=0, microsec=0):
    now = datetime.now()
    return now.replace(hour=hr, minute=min, second=sec, microsecond=microsec)


""" тело программы """
logger.add('logs\\logs.txt', format="{time: DD-MM-YY  HH:mm:ss} {level} "
                                    "{module}:{function}:{line} - {message}", rotation='00:00')
TOKEN = get_token(LOGIN, PASSWORD)

while True:
    time_now = datetime.now()
    if today_at(9) < time_now < today_at(23, 30):
        # logger.info(f'РАБОЧЕЕ ВРЕМЯ. Текущее время: {time_now.strftime("%H:%M")}')
        if check_token(TOKEN) == 'hello':
            today = date.today() + timedelta(days=1)
            all_deliveries = get_all_deliveries_today(TOKEN, ORG_ID, TERMINAL_ID)

            if not all_deliveries:
                logger.error('Не удалось получить список доставок')
                logger.info('Пауза 5 секунд')
                time.sleep(5)
            else:
                deliveries = parsed_deliveries(all_deliveries)
                cooking_deliveries_ls = deliveries_cooking(deliveries)
                closed_deliveries_ls = deliveries_closed(deliveries)
                write_deliveries_to_files(all_deliveries)
                filename_cooking = 'data\\sent-wa-cooking-' + str(date.today()) + '.txt'
                cooking_wa = get_list_cooking_wa_send(filename_cooking)
                working_with_cooking(cooking_deliveries_ls, cooking_wa, filename_cooking)

                filename_closed = 'data\\sent-wa-closed-' + str(date.today()) + '.txt'
                closed_wa = get_list_closed_wa_send(filename_closed)
                working_with_closed(closed_deliveries_ls, closed_wa, filename_closed)
                logger.info('Пауза 60 секунд')
                time.sleep(60)

        else:
            TOKEN = get_token(LOGIN, PASSWORD)
            logger.info('Пауза 10 секунд')
            time.sleep(10)

    else:
        logger.info(f'Нерабочее время. Текущее время: {time_now.strftime("%H:%M")}')
        logger.info('Пауза 600 секунд')
        time.sleep(600)
