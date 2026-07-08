# Write your solution here

def who_won(game_board):
    count_one = 0
    count_two = 0

    for row in game_board :
        count_one += row.count(1)
        count_two += row.count(2)

    if count_one > count_two :
        return 1

    elif count_two > count_one :
        return 2
    
    else :
        return 0