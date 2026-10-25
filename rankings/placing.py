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