# Write your solution here
from random import choice

def roll(die: str): 
    if die == "A":
        options = [3,3,3,3,3,6]
        rand = choice(options)
    elif die == "B":
        options = [2,2,2,5,5,5]
        rand = choice(options)
    elif die == "C":
        options = [1,4,4,4,4,4]
        rand = choice(options)
    return rand

def play(die1, die2, times):
    die1_win = 0
    die2_win = 0
    for i in range(times):
        die1_res = roll(die1)
        die2_res = roll(die2)
        if die1_res > die2_res:
            die1_win += 1
        elif die2_res > die1_res:
            die2_win += 1
    draw = times - (die1_win + die2_win)
    return (die1_win, die2_win, draw)


if __name__ == "__main__":
    for i in range(20):
        print(roll("A"), " ", end="")
    print()

    for i in range(20):
        print(roll("B"), " ", end="")
    print()

    for i in range(20):
        print(roll("C"), " ", end="")
    print()
    
    result = play("A", "C", 1000)
    print(result)
    result = play("B", "B", 1000)
    print(result)