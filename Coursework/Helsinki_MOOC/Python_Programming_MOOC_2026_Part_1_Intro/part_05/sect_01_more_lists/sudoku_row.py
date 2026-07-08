#optimized solution
#def row_correct(sudoku: list, row_no: int) -> bool:
#    # Filter out empty cells (0) from the row
#    filled_numbers = [num for num in sudoku[row_no] if num != 0]
#    
#    # A row is correct if its length equals the length of its unique elements
#    return len(filled_numbers) == len(set(filled_numbers))
#optimized solution




#def row_correct(sudoku: list, row_no: int):
#    seen_numbers = []
#    for number in sudoku[row_no]:
#        if number > 0 and number in seen_numbers:
#            return False
#        seen_numbers.append(number)    
#    return True



def row_correct(sudoku: list, row_no: int):
    row = sudoku[row_no]
    seen_numbers = []
    for num in row:
        if num == 0:
            continue
        if num in seen_numbers:
            return False
        seen_numbers.append(num)    
    return True