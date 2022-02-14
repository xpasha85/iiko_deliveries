from datetime import date, datetime
import requests
from loguru import logger
import json
import os.path


def check_token(token, msg='hello'):
    """Проверить токен. Если проверка пройдена вернет msg"""
    try:
        response = requests.get(f"https://iiko.biz:9900/api/0/auth/echo?msg={msg}&access_token=" + token,
                                timeout=5)
        if response.ok:
            # logger.info('Проверка токена. Сервер отвечает')
            return response.json()
        else:
            # logger.error('Проверка токена. '+response.text)
            return None
    except Exception as error:
        logger.error('Проверка токена. Ошибка соединения с сервером.' + repr(error))


def get_token(login, password):
    """Получить токен"""
    try:
        url = 'https://iiko.biz:9900/api/0/auth/access_token?user_id=' + \
              login + "&user_secret=" + password
        response = requests.get(url, timeout=5)
        if response.ok:
            logger.info('Получение токена. Токен получен ')
            return response.json()
        else:
            logger.error('Получение токена. Response <> 200')
            return response.json()
    except Exception as error:
        logger.error('Получение токена. Ошибка соединения с сервером.' + repr(error))


def get_all_deliveries_by_dates(token, org_id, terminal_id, date_from, date_to):
    """Получить список заказов на определеные даты"""
    url = f'https://iiko.biz:9900/api/0/orders/deliveryOrders?access_token={token}' \
          f'&organization={org_id}&dateFrom={date_from}&dateTo={date_to}&deliveryTerminalId={terminal_id}'
    try:
        response = requests.get(url, timeout=5)
        if response.ok:
            # logger.info('Список доставок получен')
            return response.json()
        else:
            logger.error('Ошибка получения списка доставок (Response <> 200)')
    except Exception as error:
        logger.error('Получение доставок. Ошибка соединения с сервером.' + repr(error))


def get_all_deliveries_today(token, org_id, terminal_id):
    """Получить список заказов на сегодня"""
    response = get_all_deliveries_by_dates(token, org_id, terminal_id, date.today(), date.today())
    if response:
        return response
    else:
        logger.error('Не возможно получить список заказов на сегодня')


def get_ard_from_dict(delivery):
    """Возвращает словарь из улицы, дома, квартиры|офиса.
        На вход подается доставка полностью"""
    address = {'street': delivery['address']['street'],
               'home': delivery['address']['home'],
               'apartment': delivery['address']['apartment']
               }
    return address


def get_parsed_order_amount(delivery):
    """Возвращает список блюд заказа в виде: Блюдо - количесвтво.
        На вход подается доставка полностью"""
    items = delivery['items']
    ls = []
    for item in items:
        name = item['name']
        amount = int(item['amount'])
        ls.append(name + ' - ' + str(amount) + ' шт.')
    return ls


def get_customer_payment_type(delivery):
    """Возвращает выбранный тип оплаты.
        На вход подается доставка полностью"""
    payments = delivery['payments']
    payment = 'notAssigned'
    for item in payments:
        payment = item['paymentType']['code']
        break
    return payment


def get_customer_marketing_source(delivery):
    """Возвращает источник рекламы.
        На вход подается доставка полностью"""

    # cancelTime = delivery['cancelTime']
    marketing = delivery['marketingSource']
    if marketing != None:
        return marketing['name']
    else:
        return 'empty'


def parsed_deliveries(deliveries):
    """Возвращает распарсенный список заказов"""

    items = deliveries['deliveryOrders']
    ls = []
    customer = {}
    for item in items:
        customer['number'] = item['number']
        if item['customer'] != None:
            customer['name'] = str(item['customer']['name']).title()
        else:
            customer['name'] = str(item['customerName']).title()
        customer['phone'] = item['customerPhone'][1:]
        customer['orderType'] = item['orderType']['orderServiceType']
        if customer['orderType'] == 'DELIVERY_BY_COURIER':
            customer['address'] = get_ard_from_dict(item)
        else:
            customer['address'] = {}
        customer['status'] = item['status']
        if customer['status'] == 'Закрыта':
            customer['closeTime'] = item['closeTime']
        else:
            customer['closeTime'] = ''
        customer['createdTime'] = item['createdTime']
        customer['deliveryDate'] = item['deliveryDate']
        created_time = datetime.strptime(customer['createdTime'], '%Y-%m-%d %H:%M:%S')
        delivery_time = datetime.strptime(customer['deliveryDate'], '%Y-%m-%d %H:%M:%S')
        time_in_second_before_delivery = (delivery_time - created_time).seconds
        if customer['orderType'] == 'DELIVERY_BY_COURIER':
            difference_seconds = 6000
        else:
            difference_seconds = 3900
        if time_in_second_before_delivery > difference_seconds:
            customer['pre-order'] = True
        else:
            customer['pre-order'] = False
        if item.get('printTime'):
            customer['printTime'] = item['printTime']
        else:
            customer['printTime'] = ''
        customer['summ'] = item['sum']
        customer['discount'] = item['discount']

        customer['payment'] = get_customer_payment_type(item)
        customer['items'] = get_parsed_order_amount(item)
        customer['marketing'] = get_customer_marketing_source(item)

        ls.append(customer.copy())
    return ls


def deliveries_preorder(deliveries):
    """Возвращает распаресенный список предзаказов"""
    ls = []
    for item in deliveries:
        if item['pre-order']:
            ls.append(item)
    return ls


def deliveries_cooking(deliveries):
    """Возвращает распаресенный список заказов
    со статусом 'Готовится'"""
    ls = []
    for item in deliveries:
        if item['status'] == 'Готовится':
            ls.append(item)
    return ls


def deliveries_closed(deliveries):
    """Возвращает распаресенный список заказов
    со статусом 'Закрыт'"""
    ls = []
    for item in deliveries:
        if item['status'] == 'Закрыта':
            ls.append(item)
    return ls


def get_list_cooking_wa_send(filename):
    """
        Получаем список доставок (ID) из файла по которым были отпрвлены сообщения
        в WhatsApp. Если файл пуст - создаем.
    """
    logger.info('Подгружаем список доставок ("Готовится") по которым отправлено сообщение')
    ls = []
    if os.path.exists(filename):
        with open(filename, 'r') as file:
            ls = list(json.load(file))
    else:
        with open(filename, 'w') as file:
            json.dump(ls, file)
    return ls


def get_list_closed_wa_send(filename):
    """
        Получаем список доставок (ID) из файла по которым были отпрвлены сообщения
        в WhatsApp. Если файл пуст - создаем.
    """
    logger.info('Подгружаем список доставок ("Закрыта") по которым отправлено сообщение')
    ls = []
    if os.path.exists(filename):
        with open(filename, 'r') as file:
            ls = list(json.load(file))
    else:
        with open(filename, 'w') as file:
            json.dump(ls, file)
    return ls


def write_deliveries_to_files(deliveries):
    """Внутренняя функция для вывода состояний доставок в файлы.
    На вход подается JSON - ответ от сайта"""
    data = parsed_deliveries(deliveries)
    path = 'data\\'
    with open(path + 'data.txt', 'w') as outfile:
        json.dump(deliveries, outfile, indent=4, ensure_ascii=False)
    with open(path + 'parsed.txt.', 'w') as outfile:
        json.dump(data, outfile, indent=4, ensure_ascii=False)
    with open(path + 'cooking.txt.', 'w') as outfile:
        json.dump(deliveries_cooking(data), outfile, indent=4, ensure_ascii=False)
    with open(path + 'closed.txt', 'w') as outfile:
        json.dump(deliveries_closed(data), outfile, indent=4, ensure_ascii=False)
    with open(path + 'pre-order.txt', 'w') as outfile:
        json.dump(deliveries_preorder(data), outfile, indent=4, ensure_ascii=False)


def is_send_wa(delivery, ls, status='Готовится'):
    """Проверяет есть ли декущая доставка в списке доставок по
        которым были отправлены сообщения. """
    flag = False
    for item in ls:
        if delivery['number'] == item['id']:
            flag = True
            break
    if not flag:
        logger.info(f'Найдена новая доставка "{status}".')
    return flag


def check_whatsapp(token, phone):
    """Проверяет есть ли вотсап на указаном номере телефона на вход номер в формате 7999ХХХХХХХ"""
    url = f"https://chatter.salebot.pro/api/{token}/check_whatsapp?phone={phone}"
    response = requests.get(url)
    if response.status_code == 200:
        exists = dict(response.json())['exists']
        if exists:
            logger.info('WhatsApp есть ' + phone)
        else:
            logger.error('WhatsApp нету! ' + phone)
        return exists
    else:
        logger.error('Ошибка проверки вотсапа на номере ' + response.text)
        return False


def get_id_client_by_whatsapp(token, phone):
    """
        Метод вернет идентификатор клиента для выполнения запросов к API,
        если вы знаете номер телефона клиента в Whatsapp.
    """
    url = f'https://chatter.salebot.pro/api/{token}/whatsapp_client_id?phone={phone}'
    response = requests.get(url)
    if response.status_code == 404:
        logger.info('SALEBOT. Клиент отсутствует в базе')
        return 'NO'
    elif response.status_code == 200:
        logger.info('SALEBOT. Клиент найден в базе.')
        return response.json()['client_id']


def get_variables_by_id_salebot(token, client_id):
    """
       Возвращает список переменных по id клиента SALEBOT. Тип - словарь
    """
    url = f'https://chatter.salebot.pro/api/{token}/get_variables?client_id={client_id}'
    response = requests.get(url)
    if response.status_code != 200:
        logger.error('SALEBOT. Ошибка получения переменных по client_id')
        return 'NO'
    elif response.status_code == 200:
        status = dict(response.json())
        if status.get('status') == 'client_not_found':
            logger.error('SALEBOT. Неверный client_id')
            return 'NO'
        else:
            logger.info('SALEBOT. Переменные успешно получены по client_id')
            return response.json()


def write_variables_by_id_salebot(token, client_id, variables):
    """
        Записываем переменные клиенту SALEBOT по ID клиента
    """
    url = f'https://chatter.salebot.pro/api/{token}/save_variables'
    params = {"client_id": client_id,
              "variables": variables}
    response = requests.post(url, json=params)
    if response.status_code != 200:
        logger.info('SALEBOT. Ошибка записи переменных ')
        return 'NO'
    else:
        logger.info('SALEBOT. Переменные добавлены к клиенту')
        return 'YES'


def create_client_in_salebot(token, phone):
    """
        создаем клиента в SALEBOT по номеру телефона
    """
    url = f'https://chatter.salebot.pro/api/{token}/load_clients'
    params = [{
        "platform_id": phone,
        "group_id": "22661",
        "client_type": 6
    }]
    response = requests.post(url, json=params)
    if response.status_code != 200:
        logger.info('SALEBOT. Ошибка создания клиента по номеру телефона')
        return 'NO'
    else:
        # response.status_code == 200:
        items = response.json().get('items')
        client_id = ''
        for item in items:
            client_id = item.get('id')
        logger.info('SALEBOT. Клиент успешно создан')
        return str(client_id)


def migrate_to_special_block(token, phone, block, is_test: bool):
    """Переводим клиента в нужный block в SALEBOT"""
    url = f'https://chatter.salebot.pro/api/{token}/whatsapp_message'
    if is_test:
        phone = '79147122227'
    params = {"phone": phone, "message_id": block}
    response = requests.post(url, json=params)
    if response.status_code == 200:
        logger.info(f'SALEBOT. Выполнено перемещние в блок {block} клиента {phone}')
        return 'OK'
    else:
        logger.error(f'SALEBOT. Ошибка перемещения в блок {block} клиента {phone}')
        return 'ERROR'


def send_whatsapp(token, phone, text, is_test: bool):
    """
        Отправка вотсап через Salebot.
        Если is_test=True, отправка всех сообщений на тестовый номер
    """
    url = f'https://chatter.salebot.pro/api/{token}/whatsapp_message'
    if is_test:
        phone = '79147122227'
    # "message_id": '3126925' - добавить в параметр ниже для перехода в блок с определенным ID
    params = {"message": text, "phone": phone}
    response = requests.post(url, json=params)
    if response.status_code == 200:
        logger.info('Сообщение успешно отправлено на WhatsApp на номер ' + phone)
        return 'OK'
    else:
        logger.error('Ошибка отправки сообщения на WhatsApp ' + phone)
        return 'ERROR'


def making_text_for_message(delivery, type_text, type_of_direction=''):
    """
        Возвращает форматированный тект для сообщения.
        type_text:
            'pickup_in_time' - самовывоз на ближайщее
            'courier_in_time' - доставка курьером на ближайшее
            'pickup_pre_order_print' - самовывоз предзаказ (передан на кухню)
            'courier_pre_order_print' - доставка курьером предзаказ (передан на кухню)
        type_of_direction:
            'Брускетта' - заказ брускетта
            'ЧикенАзия' - заказ с ЧикенАзия который готовится на Точке
    """
    # выбираем по какому направлению будет формироваться сообщение: Брускетта, ЧикенАзия, БамбукКафе
    if type_of_direction == 'Брускетта':
        marketing = 'Брускетта'
    elif type_of_direction == 'ЧикенАзия':
        marketing = 'ЧикенАзия'
    else:
        marketing = 'BambookCafe'

    number = delivery['number']
    name = delivery['name']
    # phone = delivery['phone']
    order_type = delivery['orderType']
    address = delivery['address']
    adr = ""

    # формируем адрес доставки (пусто если самовывоз)
    if order_type == 'DELIVERY_BY_COURIER':
        street = address['street']
        home = address['home']
        kv = address['apartment']
        adr = f'ул.{street}, д.{home}'
        if kv != '':
            adr += ', кв. ' + kv
    # ----------------------------------------------

    summ = int(delivery['summ'])
    payment = str(delivery['payment'])
    if payment == 'CARD':
        payment = 'Оплата: Картой курьеру \n'
    elif payment == 'CASH':
        payment = 'Оплата: Наличные \n'
    elif payment == 'SITE':
        payment = 'Оплата: Оплачено онлайн \n'
    else:
        payment = ''
    items = list(delivery['items'])
    order_positions = ''
    for item in items:
        order_positions += item + '\n'

    # формируем переменные даты и времени доставки для предзаказов
    str_days = ''
    str_time = ''
    if type_text == 'courier_pre_order_print' or type_text == 'pickup_pre_order_print':
        delivery_time = datetime.strptime(delivery['deliveryDate'], '%Y-%m-%d %H:%M:%S')
        print_time_str = delivery['printTime']
        if print_time_str != '':
            print_time = datetime.strptime(delivery['printTime'], '%Y-%m-%d %H:%M:%S')
        else:
            # если PrintTime пустая строка, то берем время из даты\времени создания заказ
            print_time = datetime.strptime(delivery['createdTime'], '%Y-%m-%d %H:%M:%S')
        time_between = delivery_time - print_time
        if time_between.days == 1:
            str_days = 'завтра'
        elif time_between.days > 1:
            str_days = delivery_time.strftime('%d.%m')
        else:
            str_days = 'сегодня'
        str_time = delivery_time.strftime('%H:%M')
    # --------------------------------------------------------------------

    text = ''
    if type_text == 'courier_in_time':
        text = f'{name}, здравствуйте 👋\n\n' \
               f'Ваш заказ уже принят и оформлен в {marketing} ✅\n' \
               f'Приготовим 👨‍🍳 и доставим 🚗 для Вас в течение 60-90 минут 🙌 \n\n' \
               f'Ваш заказ № {number}:\n' + order_positions + '\n' \
                                                              f'Общая сумма заказа: {summ} руб.\n' + payment + \
               f'Адрес: {adr} \n\n' \
               f'Благодарим Вас за заказ ❤'
    if type_text == 'pickup_in_time':
        text = f'{name}, здравствуйте 👋\n\n' \
               f'Ваш заказ уже принят и оформлен в {marketing} ✅ \n' \
               f'Приготовим 👨‍🍳 для Вас в течение 40-60 минут 🙌 \n\n' \
               f'Ваш заказ № {number}:\n' + order_positions + '\n' \
                                                              f'Общая сумма заказа: {summ} руб.\n' + payment + \
               f'Благодарим Вас за заказ ❤'
    if type_text == 'courier_pre_order_print':
        text = f'{name}, здравствуйте 👋\n\n' \
               f'Ваш заказ уже принят и оформлен в {marketing} ✅\n' \
               f'Приготовим 👨‍🍳 и доставим 🚗 для Вас {str_days} в {str_time} 🙌 \n\n' \
               f'Ваш заказ № {number}:\n' + order_positions + '\n' \
                                                              f'Общая сумма заказа: {summ} руб.\n' + payment + \
               f'Адрес: {adr} \n\n' \
               f'Благодарим Вас за заказ ❤'
    if type_text == 'pickup_pre_order_print':
        text = f'{name}, здравствуйте 👋\n\n' \
               f'Ваш заказ уже принят и оформлен в {marketing} ✅ \n' \
               f'Приготовим 👨‍🍳 для Вас {str_days} к {str_time} 🙌 \n\n' \
               f'Ваш заказ № {number}:\n' + order_positions + '\n' \
                                                              f'Общая сумма заказа: {summ} руб.\n' + payment + \
               f'Благодарим Вас за заказ ❤'
    return text


def send_whatsapp_cooking(token, delivery, is_test: bool):
    """
        Отправка вотсап сообщения клиенту, чьи доставки переведены в
        статус "Готовится".
    """
    phone = delivery['phone']
    if delivery['orderType'] == 'DELIVERY_BY_COURIER':
        if not delivery['pre-order']:
            text = making_text_for_message(delivery, 'courier_in_time')
        else:
            text = making_text_for_message(delivery, 'courier_pre_order_print')
    else:
        if not delivery['pre-order']:
            text = making_text_for_message(delivery, 'pickup_in_time')
        else:
            text = making_text_for_message(delivery, 'pickup_pre_order_print')
    if send_whatsapp(token, phone, text, is_test) == 'OK':
        return 'OK'
    else:
        return 'ERROR'
