from cache_for_fastapi import CacheCalendar


@router.get('/events', summary='Получить события или событие по uid')
async def get_event(start_date: datetime | None = None,
                    end_date: datetime | None = None,
                    room_name: str = 'Календарь',
                    uid: Optional[int] = None,
                    user: UserResponse = Depends(get_user)) -> DictResponse | ListResponse:
    """## Endpoint для получения событий или событие по uid
    ### Parameters:
        start_date: datetime -- даты начала поиска событий 2024-10-07T00:00:00
        start_date: datetime -- даты окончания поиска событий 2024-10-27T23:59:59
        room_name: str -- название календаря для получения события
        uid: Optional[int] -- уникальный идентификатор события
        user: User -- Объект пользователя, приходит извне по grpc"""
    try:
        start_date = (start_date.replace(hour=0, minute=0, second=0, microsecond=0) if start_date else
                      datetime.now().replace(hour=0, minute=0, second=0, microsecond=0))
        end_date = (end_date.replace(hour=23, minute=59, second=59, microsecond=0) if end_date else
                    (datetime.now() + timedelta(days=30)).replace(hour=23, minute=59, second=59, microsecond=0))
        if start_date > end_date:
            raise ValueError('Дата начала поиска не может быть раньше даты окончания поиска')
        # TODO Пример применения кэша
        cache_util = (CacheCalendar(prefix=f'{start_date}_{end_date}_{room_name}', postfix='all_events')
                      if check_room(room_name)
                      else CacheCalendar(prefix=f'{start_date}_{end_date}_{user.auto_card}', postfix='all_events'))
        if (result := await cache_util.get_cached_router()) and not uid:
            return ListResponse(result=result)

        rm = await get_room_manager(room_name) if check_room(room_name) else await get_room_manager(room_name, user)
        if uid:
            result: Dict[EventEntityDetail] = await rm.find_event(uid, user)
            return DictResponse(result=result)
        result = await rm.all_events(start=start_date, end=end_date)
        await cache_util.cached_router(result)
        return ListResponse(result=result)
    except NotFoundEvent as error:
        logger.error(error)
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error))
    except Exception as error:
        logger.error(error)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error))


@router.post('/create_event', summary='Создать событие в календаре для переговорок',
             description=description_post_create_event)
async def create_event(data: CreateEvent,
                       room_name: CalendarName,
                       attendees: List[Attendee],
                       user: UserResponse = Depends(get_user)) -> DictResponse:
    """
    ## Endpoint для создания события в календаре для переговорок
    ### Parameters:
        data: CreateEvent -- данные для создания события
        room_name: CalendarName -- название календаря для получения события
        attendees: list[Attendee] -- Участники события, БЕЗ создателя
        user: User -- Объект пользователя, который создаёт событие, приходит извне по grpc"""
    try:
        attendees.append(Attendee(auto_card=user.auto_card,
                                  email=user.email,
                                  name=user.name,
                                  name_i=user.name_i,
                                  name_o=user.name_o))
        room = room_name.calendar
        rm = await get_room_manager(room) if check_room(room) else await get_room_manager(room, user)
        result = await rm.create_event(data=data, user=user, attendees=attendees)
        # TODO Пример применения кэша
        await CacheCalendar().delete_all_cache_calendar()
        await notification_user.notify_attendees_when_creating(attendees=attendees, data=data, room_name=room_name)
        return DictResponse(result=result)
    except (AuthenticationError, NoEmailInUser) as error:
        logger.error(error)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(error))
    except Exception as error:
        logger.error(error)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error))


@router.get('/get_all_merged_calendar', summary='Возвращает все календари для переговорок')
async def get_all_calendar(day: datetime | None = None,
                           user: UserResponse = Depends(get_user)):
    """## Endpoint возвращает список всех календарей для переговорок
    ### Parameters:
        day: datatime -- день за который router вернёт все календари 2024-10-07T00:00:00
        user: User -- Объект пользователя, который создаёт событие, приходит извне по grpc"""
    try:
        day = day if day else datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        # TODO Пример применения кэша
        if result := await CacheCalendar(prefix=day, postfix='all_calendar').get_cached_router():
            return ListResponse(result=result)
        try:
            rm_user = await get_room_manager(user=user)
            user_calendar = await rm_user.all_calendar_user()
        except ValueError:
            user_calendar = None
        rm = await get_room_manager()
        add_percent = await rm.add_percent_to_all_calendar(day)
        result = [AllCalendarName(user_calendar=user_calendar, service_calendar=add_percent)]
        # TODO Пример применения кэша
        await CacheCalendar(prefix=day, postfix='all_calendar').cached_router(result)
        return ListResponse(result=result)
    except (AuthenticationError, NoEmailInUser) as error:
        logger.error(error)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(error))
    except Exception as error:
        logger.error(error)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error))


@router.delete('/delete_event', summary='Удаляет событие в календаре для переговорок')
async def delete_one_event(uid: int,
                           room_name: str = 'Календарь',
                           user: UserResponse = Depends(get_user)) -> DictResponse:
    """## Endpoint удаляет событие в календаре для переговорок
    ### Parameters:
        uid: int -- uid события для удаления
        room_name: CalendarName -- Календарь для бронирования переговорки
        user: User -- Объект пользователя, который создаёт событие, приходит извне по grpc"""
    try:
        await validate_user_grpc(user)
        rm = await get_room_manager(room_name) if check_room(room_name) else await get_room_manager(room_name, user)
        result = await rm.delete_event(uid=uid, user_id=user.auto_card)
        # TODO Пример применения кэша
        await CacheCalendar().delete_all_cache_calendar()
        return DictResponse(result=result)
    except ServiceError as error:
        logger.error(error)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(error))
    except NotFoundEvent as error:
        logger.error(error)
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error))
    except Exception as error:
        logger.error(error)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error))


@router.get('/free_rooms', summary='Возвращает свободные комнаты по заданному времени')
async def get_free_rooms(check_start: datetime | None = None,
                         check_end: datetime | None = None) -> ListResponse:
    """## Endpoint для возврата свободных комнат по заданному времени
    ### Parameters:
        check_start: datetime -- datetime начала проверки 2024-10-07T00:00:00
        check_end: datetime -- datetime окончания проверки 2024-10-07T01:00:00"""
    try:
        # TODO Пример применения кэша
        if (result := await CacheCalendar(postfix='free_rooms').get_cached_router()) and not check_start:
            return ListResponse(result=result)
        check_start = check_start if check_start else datetime.now()
        check_end = check_end if check_end else datetime.now() + timedelta(hours=1)
        rm = await get_room_manager()
        result = await rm.free_rooms(check_start, check_end)
        # TODO Пример применения кэша
        await CacheCalendar(postfix='free_rooms').cached_router(result)
        return ListResponse(result=result)
    except Exception as error:
        logger.error(error)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error))


@router.post('/accept_decline', summary='Принять/отказать встречу')
async def accept_decline_event(is_accept: bool, event: EventEntityDetail,
                               user=Depends(get_user),
                               room_name='Календарь'):
    """## Endpoint для возврата свободных комнат по заданному времени
    ### Parameters:
        accept: Literal['yes', 'no'] -- принять или отказаться от встречи
        user: User -- Объект пользователя, который создаёт событие, приходит извне по grpc
        room_name: str --  Календарь в которой принять или отказать встречу"""
    try:
        await validate_user_grpc(user)
        rm = await get_room_manager(room_name) if check_room(room_name) else await get_room_manager(room_name, user)
        result = await rm.accept_event_service(event=event, is_accept=is_accept)
        # TODO Пример применения кэша
        await CacheCalendar().delete_all_cache_calendar()
        return result
    except Exception as error:
        logger.error(error)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error))


@router.post('/update', summary='Редактировать встречу, где вы создатель')
async def update_event(data: UpdateEventSchema,
                       attendees: List[Attendee],
                       event: EventEntityDetail,
                       user=Depends(get_user),
                       room_name='Календарь'):
    """## Endpoint для изменения события в календаре
    ### Parameters:
        data: CreateEvent -- данные для изменения
        event: EventEntityDetail -- полные данные события, которое нужно изменить
        room_name: str --  календарь события"""
    try:
        await validate_user_grpc(user)
        # Оба календаря "Календарь"
        if room_name == data.new_room_name == 'Календарь':
            rm = await get_room_manager(room_name, user)
            result = await rm.update_event_service(data, event, user, attendees)
        # Оба календаря сервисные и одинаковые
        elif (room_name == data.new_room_name) and (check_room(room_name) and check_room(data.new_room_name)):
            rm = await get_room_manager(room_name)
            result = await rm.update_event_service(data, event, user, attendees)
        # Оба календаря сервисные, но разные
        elif (room_name != data.new_room_name) and (check_room(room_name) and check_room(data.new_room_name)):
            rm = await get_room_manager(room_name)
            await rm.delete_event(uid=event.uid_event, user_id=user.auto_card)
            rm = await get_room_manager(data.new_room_name)
            result = await rm.create_event(data=data, user=user, attendees=attendees)
        # Изначальный "Календарь", а второй сервисный
        elif room_name == 'Календарь' and check_room(data.new_room_name):
            rm = await get_room_manager(room_name, user)
            await rm.delete_event(uid=event.uid_event, user_id=user.auto_card)
            rm = await get_room_manager(data.new_room_name)
            result = await rm.create_event(data=data, user=user, attendees=attendees)
        # Изначальный сервисный, а второй "Календарь"
        elif check_room(room_name) and data.new_room_name == 'Календарь':
            rm = await get_room_manager(room_name)
            await rm.delete_event(uid=event.uid_event, user_id=user.auto_card)
            rm = await get_room_manager(data.new_room_name, user)
            result = await rm.create_event(data=data, user=user, attendees=attendees)
        else:
            raise FoundUpdateEventException()

        # TODO Пример применения кэша
        await CacheCalendar().delete_all_cache_calendar()
        return result
    except Exception as error:
        logger.error(error)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error))


@router.get('/get_time_block', summary='Возвращает блоки-времени для бронирования переговорок')
async def get_time_block(day: datetime | None = None,
                         room_name: str = 'Бильярдная',
                         user: UserResponse = Depends(get_user)) -> DictResponse | ListResponse:
    """## Endpoint для получения занятости переговорки по временным-блокам, работает только для сервисных календарей
    ### Parameters:
        day: datatime -- день за который router вернёт блоки-времени 2024-10-07T00:00:00
        room_name: str -- название календаря для формирования списка блоков"""
    try:
        day = day if day else datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        # TODO Пример применения кэша
        if result := await CacheCalendar(prefix=f'{day}_{room_name}', postfix='get_time_block').get_cached_router():
            return ListResponse(result=result)
        rm = await get_room_manager(room_name)
        result = await rm.check_time_block(day)
        # TODO Пример применения кэша
        await CacheCalendar(prefix=f'{day}_{room_name}', postfix='get_time_block').cached_router(result)
        return ListResponse(result=result)
    except Exception as error:
        logger.error(error)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error))
