# Cache для router в FastApi

## Данный проект сделан на интеграции календаря построенного на протоколе ximss, его легко можно поменять под другие реализации routers

## Реализованы четыре основных метода для работы с кэшем: 
- `cached_router` -- закэшировать роутер, использует prefix и postfix (полученные при инициализации класса CacheCalendar)
- `get_cached_router` -- получает кэш по prefix и postfix
- `delete_cache` -- удаляет кэш по prefix и postfix
- `delete_all_cache_calendar` -- удаляет все кэши по postfix, нужно вручную внести в list_postfix

## Стек проекта:
- `pendulum` -- для преобразования datetime, поддерживает `Python = ^3.8`
- `FastApi` -- непосредственно FastApi, используется для jsonable_encoder, при переносе проекта на другие фреймворки или для другого использования, нужно будет применять другое encoder
- `Starlette` -- данный пакет входит в FastApi, так же используется для encoder

## FastApi и Starlette в проекте используются для типизации и encoder, так что их легко можно будет заменить на свою реализацию в `json.dumps`
