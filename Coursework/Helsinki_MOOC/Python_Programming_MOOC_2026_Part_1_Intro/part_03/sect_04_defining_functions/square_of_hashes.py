#wr4ite a function with a loop that counts from index = 1 to x, printing x times with widht = x
def hash_square(x) :
    index = 1
    while index <= x :
        print("#" * x)
        index += 1
if __name__ == "__main__":
    hash_square(5)