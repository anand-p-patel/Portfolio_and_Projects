# Write your solution here



def print_sudoku(sudoku):
    for row_index, row in enumerate(sudoku):
        if row_index > 0 and row_index % 3 == 0:
            print()  # blank line between row groups
        for col_index, square in enumerate(row):
            if col_index > 0 and col_index % 3 == 0:
                print(" ", end="")  # extra space between column groups
            if square > 0:
                print(square, end=" ")
            else:
                print("_", end=" ")
        print()


def add_number(sudoku: list, row_no: int, column_no: int, number: int):
    sudoku[row_no][column_no] = number

def copy_and_add(sudoku, row_no, column_no, number):
    new_grid = [row[:] for row in sudoku]
    new_grid[row_no][column_no] = number
    
    grid_copy = new_grid
    return grid_copy













if __name__ == "__main__":
    sudoku  = [
    [0, 0, 0, 0, 0, 0, 0, 0, 0],
    [0, 0, 0, 0, 0, 0, 0, 0, 0],
    [0, 0, 0, 0, 0, 0, 0, 0, 0],
    [0, 0, 0, 0, 0, 0, 0, 0, 0],
    [0, 0, 0, 0, 0, 0, 0, 0, 0],
    [0, 0, 0, 0, 0, 0, 0, 0, 0],
    [0, 0, 0, 0, 0, 0, 0, 0, 0],
    [0, 0, 0, 0, 0, 0, 0, 0, 0],
    [0, 0, 0, 0, 0, 0, 0, 0, 0]
    ]

    grid_copy = copy_and_add(sudoku, 0, 0, 2)
    print("Original:")
    print_sudoku(sudoku)
    print()
    print("Copy:")
    print_sudoku(grid_copy)

