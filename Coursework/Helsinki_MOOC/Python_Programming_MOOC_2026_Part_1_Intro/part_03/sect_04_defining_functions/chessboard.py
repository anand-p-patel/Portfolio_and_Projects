#define a functin that iterates through a loop up to x times, printing x times with width of x
def chessboard(x):
    index = 1
    white = "0"
    black = "1"
    while index <= x :
        if index % 2 == 0 :
            board = (white + black)*x
        else :
            board = (black + white)*x
        index += 1
        print(board[:x])

# Testing the function
if __name__ == "__main__":
    chessboard(3)
