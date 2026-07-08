# Write your solution here
# Write your solution here

def row_correct(sudoku: list, row_no: int):
    seen_numbers = []
    for number in sudoku[row_no]:
        if number > 0 and number in seen_numbers:
            return False
        seen_numbers.append(number)    
    return True

def column_correct(sudoku, column_no):
    numbers = []
    for row in sudoku:
        number = row[column_no]
        if number > 0 and number in numbers:
            return False
        numbers.append(number)
    return True


def block_correct(sudoku, row_no, column_no):
    numbers = []
    seen_numbers = []
    for row in range (row_no, row_no+3):
        for col in range(column_no, column_no+3):
            number = sudoku[row][col]
            if number != 0:
                if number in numbers:
                    return False
                numbers.append(number)
    return True




def sudoku_grid_correct(sudoku):
    for row_no in range(len(sudoku)):
        if not row_correct(sudoku, row_no):
            return False
    for column_no in range(len(sudoku)):
        if not column_correct(sudoku, column_no):
            return False
    for row_no in range(0, len(sudoku), 3):
        for column_no in range(0, len(sudoku), 3):
            if not block_correct(sudoku, row_no, column_no):
                return False
    return True