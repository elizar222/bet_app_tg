# Запуск на сервере 24/7

Нужно: VPS с Ubuntu 22.04/24.04 (1 ГБ RAM хватает) и домен (или поддомен),
у которого A-запись указывает на IP сервера.

## 1. Установка

```bash
curl -fsSL https://get.docker.com | sh
git clone https://github.com/elizar222/bet_app_tg.git /opt/hedge-terminal
cd /opt/hedge-terminal
```

## 2. Настройки

Скопируйте на сервер свой `bot/.env` (тот же, что на ПК) и поменяйте в нём:

```
WEBAPP_URL=            # заполнится из DOMAIN автоматически
WEB_DEV_USER_ID=0
POSTBACK_SECRET=придумайте-длинную-строку
```

Базу с ПК можно перенести: скопируйте `bot/data/bot.db` в `/opt/hedge-terminal/bot/data/`.
Бот на ПК перед этим выключите — один токен не может работать в двух местах.

## 3. Запуск

```bash
DOMAIN=terminal.example.com docker compose up -d --build
docker compose logs -f bot        # логи
```

Caddy сам получит HTTPS-сертификат. Кнопка мини-аппа в боте переключится на
`https://terminal.example.com` при старте.

## Обновление

```bash
cd /opt/hedge-terminal && git pull
DOMAIN=terminal.example.com docker compose up -d --build
```

## Постбеки 1win (авто-VIP)

1. Реф-ссылка в `/admin → Тексты и ссылки` должна передавать ID пользователя,
   например: `https://1wxxxx.com/?open=register&p=XXXX&sub1={tg_id}`
   — бот подставит Telegram ID вместо `{tg_id}`.
2. В кабинете партнёрки 1win укажите постбеки на регистрацию и депозит:
   `https://terminal.example.com/postback/<POSTBACK_SECRET>?sub1={sub1}&event=deposit&amount={amount}`
   (для регистрации — `event=registration`). Названия макросов `{sub1}`,
   `{amount}` возьмите из кабинета партнёрки — у разных программ они разные.
3. Когда сумма депозитов игрока достигнет порога (по умолчанию 200 000 ₽,
   меняется в `/admin → Тексты и ссылки`), он автоматически станет VIP и
   получит сообщение от бота. Статистика — `/admin → 📱 Мини-апп`.

Проверка вручную:
`curl "https://terminal.example.com/postback/<SECRET>?sub1=<ваш TG ID>&event=deposit&amount=1000"`
