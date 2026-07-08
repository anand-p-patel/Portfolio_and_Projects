# Write your solution here
from random import randint

def lottery_numbers(amount, lower, upper):
    weekly_draw = []
    while len(weekly_draw) < amount:
        new_rnd = randint(lower, upper)
        if new_rnd not in weekly_draw:
            weekly_draw.append(new_rnd)
    return(sorted(weekly_draw))