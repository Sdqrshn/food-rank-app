from django.db.models import Min
from .models import RankHistory

def next_step(others, answers):
    lo, hi = 0, len(others)
    for answer in answers:
        if lo >= hi:
            break
        mid = (lo + hi) // 2
        if answer == "win":
            hi = mid
        elif answer == "lose":
            lo = mid + 1
        else:
            lo = hi = mid + 1
    if lo >= hi:
        return "done", lo
    return "ask", (lo + hi) // 2


def score_for_position(others, position):
    above = others[position - 1].elo if position > 0 else None
    below = others[position].elo if position < len(others) else None
    if above is not None and below is not None:
        return (above + below) / 2
    if above is None and below is None:
        return 1500.0
    if above is None:
        return below + 50
    return above - 50

def record_ranks(category):
    dishes = list(category.dishes.all())
    for position, dish in enumerate(dishes, start=1):
        last = dish.history.last()
        if last is None or last.rank != position:
            RankHistory.objects.create(dish=dish, rank=position)

def move_dish(dish, position, record=True):
    others = list(dish.category.dishes.exclude(pk=dish.pk))
    position = max(0, min(position, len(others)))
    new_score = score_for_position(others, position)
    if any(abs(other.elo - new_score) < 1e-6 for other in others):
        ordered = others[:position] + [dish] + others[position:]
        total = len(ordered)
        for index, item in enumerate(ordered):
            item.elo = 1500 + (total - index) * 25
            item.save(update_fields=["elo"])
    else:
        dish.elo = new_score
        dish.save(update_fields=["elo"])
    if record:
        record_ranks(dish.category)


def apply_order(category, ordered_ids):
    for position, dish_id in enumerate(ordered_ids):
        current = list(category.dishes.all())
        if position < len(current) and current[position].id != dish_id:
            dish = next((d for d in current if d.id == dish_id), None)
            if dish:
                move_dish(dish, position, record=False)
    record_ranks(category)

def bottom_score(category, exclude_pk=None):
    dishes = category.dishes.all()
    if exclude_pk:
        dishes = dishes.exclude(pk=exclude_pk)
    lowest = dishes.aggregate(lowest=Min("elo"))["lowest"]
    return lowest - 25 if lowest is not None else 1500.0