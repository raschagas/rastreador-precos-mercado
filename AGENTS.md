# Telegram routing

Proactive alerts go only to Notificações (-1002348762774) with an explicitly
selected registered topic. Never use private chats, another group, General,
or a topic-less fallback. Keep all Telegram delivery in app/engine/notify.py.
New destinations require an owner decision and updates to settings, validation
and mocked tests. Never send real test messages during automated validation.
Keep tokens out of logs. Desktop toast behavior is independent of Telegram.
