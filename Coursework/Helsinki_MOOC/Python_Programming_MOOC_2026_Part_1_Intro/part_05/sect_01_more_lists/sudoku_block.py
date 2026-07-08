# Write your solution here

def block_correct(sudoku, row_no, col_no):
    numbers = []
    for row in range (row_no, row_no+3):
        for col in range(col_no, col_no+3):
            number = sudoku[row][col]
            if number != 0:
                if number in numbers:
                    return False
                numbers.append(number)
    return True
