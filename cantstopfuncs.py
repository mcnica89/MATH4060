# -*- coding: utf-8 -*-
"""CantStopFuncs.ipynb

Automatically generated by Colaboratory.

Original file is located at
    https://colab.research.google.com/drive/1DDDvIzL6Kfnpba-RyaJRM-kFTuh237b6
"""

import itertools
import jax.numpy as jnp
from jax import random as jrandom
from jax import nn as jnn
from jax import jit
import numpy as np
import random
import time
import sys
import jax

'''Implementation of the board game "CANT STOP"

How the game is represented in Python:

-----Game parameters (that do not change while the game is being played)

N_PLAYERS
   A postive integer
  This is the number of players playing
  In the classic game rules, N_Players = 4

N_COL_TO_WIN
   A positive integer
   This is the number of columns you need to claim to win the game
   In the classic game rules, N_Col_To_Win = 3

N_MAX_RUNNERS
   A positive integer
   This is the maximum number of runners you can have
   In the classic game rules, N_Max_Runners = 3

PLAYER_COL_STATE_INIT
   An vector of shape (11,) of non-negative integers
   This is the number of squares in each game column
   In the classic game rules, this is [3,5,7,9,11,13,11,9,7,5,3]

NOTE on column labelling:
   In the game, the columns are labeled 2-12 (corresponding to dice rolls)
   In Python, the columns locations are indexed 0-10
   This means that to translate from column in Python to columns in the game,
   one must often add or subtract 2 from the column indices. 

---Variables: (that represent what is going on in the game as it is played)

active_player_index
   An index from the range [0,N_PLAYERS-1] indicating whose turn it current is

player_col_state
   An array of shape (N_players,11) of integers
   Each row is the number of squares remaining for that player in each col
   NOTE: 
     This is the number of squares REMAINING, these start at PLAYER_COL_STATE_INIT
     and count DOWN to zero as the game progresses. When the get to zero, the player has claimed the column
   WARNING:
     We will not prohibit these from being negative even though it doesn't mean anything in the game
     (This can happen if the player goes past the number needed to claim the column)

illegal_col
   A vector of shape (11,) of boolean
   Contains the information on which columns are still in play
   (columns that have been claimed by a player are not legal to play in anymore)

runner_col_state
  A vector of shape (11,) of non-negative integers
  Indicates the current state of how far the runners have advanced in each column
  A zero indicates that there is no runner in that column at all
  NOTES:
   1. count_nonzero(runner_col) should not exceed N_Max_Runners for legal runner states
   2. Since player_col_state counts DOWN to 0, runner_col is SUBTRACTED from player_col_state when the player chooses to stop rolling

dice_rolls
  A vector of shape (4,) of integers [1,6] indicating the outcome of the 4 dice rolls

runner_col_choices
  A vector of shape (N_choices, 11) of non-negative integers
  Indicates the available CHOICES the player has of where the runners could be
  This corresponds to legal choices for choosing pairings of the dice
  NOTES:
    1. By the rules of the game, N_choices can be at most 6
    2. If N_choices = 0, then this indicates that there are no legal moves and the player has busted

roll_again
  A boolean on whether or not the player wants to rolls again'''

"""# Helper functions

## Dice Functions
Note that we will compress the four 6-sided dice rolls down to an integer in the range $[0,1295]$ which we call the `diceNum`. This is done by thinking of the roll as a 4 digit number in base 6.
"""

def diceRoll_to_diceNum(diceRollArray):
  '''Converts an array of shape (4,) of the four 6 sided dice to the diceNum in [0,1295]'''
  #Note: Dice rolls are assumed to be numbers 1-6 (i.e. they start at 1!)
  powersOfSix = jnp.array([1,6,36,216])
  return jnp.inner(powersOfSix, jnp.array(diceRollArray)-1)

def diceNum_to_diceRoll(diceNum):
  '''Converts the diceNum in [0,1295] to an array of an array of shape (4,) of the 4 dice rolls'''
  #Note: Dice rolls are assumed to be numbers 1-6 (i.e. they start at 1!)
  powersOfSix = jnp.array([1,6,36,216])

  return 1+(diceNum // powersOfSix) % 6

def conversionTests():
  assert( jnp.all(diceNum_to_diceRoll(diceRoll_to_diceNum(jnp.array([2,1,1,1]))) == jnp.array([2,1,1,1])) )
  assert(diceRoll_to_diceNum(diceNum_to_diceRoll(999)) == 999)
  return True

def calculate_runnerDicePairArray():
  '''Returns an array of shape (6,11,1296) which contains the possible runner locations (encoded as one hot (11,) vectors)
   for all the possible 1296 dice rolls, and 6 possible ways to pair the dice'''
  #Input:
  # Nothing!
  #Output:
  #  a boolean vector of size (6,11,1296) so that out[i,j,:] is the (11,) boolean vector of the runner locations
  #  when the dice roll #i is rolled and choice j is selected
  #  This precomputed output is used when computing the runners that can occur in the game

  #Create an array of shape (4,6,6,6,6) that contains all possible dice rolls
  #  i.e. the entry [:,a,b,c,d] = [a,b,c,d] is 4 dice rolls and a,b,c,d all run from 0 to 5
  four_dice_indices = jnp.indices((6,6,6,6)) 
 
  #Create an array with all 6 ways to choose 2 out of 4 dice
  #  Pairing 0 = choose dice 1 and dice 2
  #  Pairing 1 = choose dice 1 and dice 3 
  #  ... 
  #  Pairing 5 = choose dice 3 and dice 4
  pairing = jnp.array([[1,1,0,0],[1,0,1,0],[1,0,0,1],[0,1,1,0],[0,1,0,1],[0,0,1,1]])

  #Create an array of shape (6,6,6,6,6) which gives the value of the pairing 
  #  i.e. the (a,b,c,d,p) entry is the value of pairing p when the dice come up a,b,c,d
  four_dice_pairings = jnp.einsum("iabcd,pi->abcdp",four_dice_indices,pairing)
  
  #The same array, but of shape (6,6,6,6,6,11) now where it has been converted to a one hot encoding
  #  i.e. (a,b,c,d,p:) is an array of shape (11,) with the one hot encoding of the pairing
  four_dice_pairings_one_hot = jnn.one_hot(four_dice_pairings,11)
  flattened_but_out_of_order = jnp.reshape(four_dice_pairings_one_hot,(1296,6,11),order='F')
  return jnp.transpose( flattened_but_out_of_order, (1,2,0)) #put them in the desired order!

"""## Helper functions for dealing with runners"""

@jit
def calculate_player_N_col_claimed(player_col_state):
  ''' Calculate player "scores" (i.e. number of columns claimed) from the board state'''
  #Input:
  #  player_col_state = An int array of size (N_players, 11) showing how many entries REMAINING until column is claimed for each player
  #Output: 
  #  An int vector of size (N_players,) showing how many columns each player has claimed. (In normal rules, first to 3 columns wins) 
  return  jnp.count_nonzero(player_col_state <= 0, axis=1)

@jit
def calculate_illegal_col(player_col_state):
  '''Calculate which columns are legal from the board state (i.e. the unclaimed columns)''' 
  #Input:
  #  player_col_state = An int array of size (N_players, 11) showing how many entries REMAINING until column is claimed for each player
  #Output: 
  #  An boolean vector of size (11,) showing which columns are legal 
  return jnp.any(player_col_state <= 0, axis=0)

def calculate_col_tests():
  '''Test the calculate columns helper functions'''
  players_col_state = jnp.array([[2,3,4,5,6,7,8,9,10,11,12],[2,0,4,5,6,7,8,9,10,11,12],[2,3,0,0,0,7,8,9,10,11,12]])

  players_N_col_claimed = calculate_player_N_col_claimed(players_col_state)
  assert jnp.all(players_N_col_claimed == jnp.array([0,1,3]))

  illegal_col = calculate_illegal_col(players_col_state)
  assert jnp.all(illegal_col == jnp.array([0,1,1,1,1,0,0,0,0,0,0]))

  return True

assert calculate_col_tests()

@jit
def are_runners_legal(runner_col_states, illegal_col, N_MAX_RUNNERS=3):
  '''Checks if a batch of runner states are legal or not'''
  #Input:
  #  runner_col_states = an int vector of size (N,11) of runner positions
  #  illegal_col = a boolean vector of size (11,) with which columns are illegal
  #Output:
  #  a boolean vector of size (N,) with which of the runner_col_states are legal

  #Number of runners is legal iff there are <=N_MAX_RUNERS runners active:
  are_number_of_runners_legal = (jnp.count_nonzero(runner_col_states,axis=1) <= N_MAX_RUNNERS)

  #Check if all the runners are in legal columns
  #  In each column, either illegal_column must be 0 OR runners must be 0
  illegal_col_or_runner_is_0 = jnp.logical_or(runner_col_states == 0, illegal_col == False)
  #  This must happen in every single column
  are_runners_in_legal_col = jnp.all(illegal_col_or_runner_is_0,axis=1) 
  
  return jnp.logical_and(are_number_of_runners_legal,are_runners_in_legal_col)

def are_runners_legal_tests():
  '''Tests for the are_runners_legal function'''
  
  illegal_col = jnp.array([0,1,0,1,0,1,0,1,0,1,0],dtype=jnp.dtype('b'))
  runner_col_states = jnp.array([[1,1,0,0,0,0,0,0,0,0,0],[1,1,1,1,0,0,0,0,0,0,0],[1,0,1,0,1,0,1,0,0,0,0],[1,0,1,0,1,0,0,0,0,0,0]],dtype=jnp.dtype('u1'))
  N_MAX_RUNNERS = 3

  #In this test:
  #0: runner in illegal column -> not legal
  #1: runner in illegal column AND to many runners -> not legal
  #2: runner in all legal columns but too many runners -> not legal
  #3: runner in all legal columns and exactly 3 runners -> legal

  assert jnp.all(are_runners_legal(runner_col_states,illegal_col,N_MAX_RUNNERS) == jnp.array([False,False,False,True])) 
  return True

assert are_runners_legal_tests()

DicePairArray = calculate_runnerDicePairArray()
@jit
def generate_all_choices_and_legality(dice_num,player_col_state,runner_col_state, N_MAX_RUNNERS=3): 
  illegal_col = calculate_illegal_col(player_col_state)
  #print("illegal_col", jnp.shape(illegal_col))
  '''Computes out ALL the possible moves based on the dice and 
  whether or not they are legal based on the current state and dice'''
  #  In this version, the input is the dice_num (which is a number in [0,1295]) and 
  #  the array DiceArray are assumed to exists
  #  which is caluclated with the DiceArray function
  #Calculate all the 9 possible moves of playing both pairs (i.e. double) and with any single pair
  # (We will work out which are legal moves afterwards!)

  #Use the dice_num to lookup the runner possibilities from DiceArray
  dice_sums_with_1_cols = DicePairArray[0:3,:,dice_num]
  dice_sums_without_1_cols = DicePairArray[5:2:-1,:,dice_num]

  #print("dice_sums_with_1_cols", jnp.shape(dice_sums_with_1_cols)) 
  #print("runner_col_state", jnp.shape(runner_col_state))
  #This 5:2:-1 gets the pairings in reverse order so that they are complentary to the pairings from dice_sums_with_1
  

  double_runner_choices = runner_col_state + dice_sums_with_1_cols + dice_sums_without_1_cols
  single_runner_choices_with_1 = runner_col_state + dice_sums_with_1_cols 
  single_runner_choices_without_1 = runner_col_state + dice_sums_without_1_cols

  #print("double_runner_choices",jnp.shape(double_runner_choices))

  #Compute if the choices with both pairing played (i.e. double) are legal
  are_double_runners_legal = are_runners_legal(double_runner_choices,illegal_col, N_MAX_RUNNERS)
  #print("are_double_runners_legal",jnp.shape(are_double_runners_legal))
  #print(are_double_runners_legal)
  are_double_runners_illegal = jnp.logical_not(are_double_runners_legal)


  #The moves with a single pair are only legal if the corresponding move with both pairs is illegal 
  #  (i.e. its legal to play only one pair iff after you play it, playing the next move is not legal)
  #  This means we can compute if they are legal on their own first and then
  #  logical_and it with the double runners

  #  first check if they would be ok on their own.
  are_single_runners_with_1_ok = are_runners_legal(single_runner_choices_with_1,illegal_col, N_MAX_RUNNERS)
  are_single_runners_without_1_ok = are_runners_legal(single_runner_choices_without_1,illegal_col, N_MAX_RUNNERS)

  #  then we logical and it with the double runners to only legalize these moves if playing both was illegal
  are_single_runners_with_1_legal = jnp.logical_and(are_double_runners_illegal,are_single_runners_with_1_ok)
  are_single_runners_without_1_legal = jnp.logical_and(are_double_runners_illegal,are_single_runners_without_1_ok)
  #print("ok!")
  #Combine everything together to be outputed
  #all_runner_choices = jnp.row_stack()
  all_runner_choices = jnp.row_stack([double_runner_choices,single_runner_choices_with_1,single_runner_choices_without_1]) 
  #print("all_runner_choices", jnp.shape(all_runner_choices))
  all_runner_choices_legal = jnp.concatenate([are_double_runners_legal, are_single_runners_with_1_legal, are_single_runners_without_1_legal])
  #print("all_runner_choices_legal", jnp.shape(all_runner_choices_legal))

  return all_runner_choices, all_runner_choices_legal

def generate_all_choices_and_legality_tests():
  dice_rolls = jnp.array([1,2,3,4],dtype=jnp.dtype('u1'))
  dice_num = diceRoll_to_diceNum(dice_rolls)
  print(dice_num)
  runner_col_state = jnp.array([0,0,0,0,0,0,0,0,0,0,0],dtype=jnp.dtype('u1'))
  illegal_col = jnp.array([0,1,0,0,0,0,0,0,0,0,0],dtype=jnp.dtype('u1'))
  expected_answer = jnp.array([[0,0,0,0,0,1,0,0,0,0,0],[0,0,0,2,0,0,0,0,0,0,0],[0,0,1,0,1,0,0,0,0,0,0]], dtype=jnp.dtype('u1'))
  N_MAX_RUNNERS = 3

  actual_answer =  generate_all_choices_and_legality(dice_num,illegal_col,runner_col_state, N_MAX_RUNNERS)
  #print(actual_answer)
  return True

@jit
def update_player_col_state(active_player_index, player_col_state, runner_col_state):
  '''Move a players peices forward by the amount on the runners 
    (This is called when a player bank's their runners and ends their turn by choice)''' 
  #Input:
  #  active_player_index = index of whose turn it is
  #  player_col_state = int array of size (N_player, 11) with squares remaining in each column
  #  runner_col_state = int vector of size (11,) with runner locations
  #Output:
  #  An updated version of player_col_state where the positions have been moved up by the runners.

  #All we have to do is a subtraction, but ensure that we don't go below zero
  updated_active_player_col_state = jnp.clip(player_col_state[active_player_index] - runner_col_state, 0, None)
  #print("updated col state", jnp.shape(updated_active_player_col_state))
  #ans = player_col_state.at[active_player_index].set(updated_active_player_col_state)
  #print("ans", jnp.shape(ans))
  return player_col_state.at[active_player_index].set(updated_active_player_col_state)

def update_player_col_test():
  '''Test the update_player_col_state function'''
  player_col_state = jnp.array([[2,3,4,5,6,7,8,9,10,11,12],[2,0,4,5,6,7,8,9,10,11,12],[2,3,0,0,0,7,8,9,10,11,12]])
  runner_col_state = jnp.array([1,1,1,1,1,1,1,1,1,1,12])
  active_player_index = 1
  expected_answer = jnp.array([[2,3,4,5,6,7,8,9,10,11,12],[1,0,3,4,5,6,7,8,9,10,0],[2,3,0,0,0,7,8,9,10,11,12]])
  
  assert jnp.all(update_player_col_state(active_player_index, player_col_state, runner_col_state)==expected_answer)
  return True

assert update_player_col_test()

"""# Main game simulator

## Three simple AIs

Note that the AIs always return a tuple choice_index, roll_again 

choice_index = a number 0-8 indicating which choice they want to make 

roll_again = a boolean of whether or not they want to roll again
"""

@jit
def pure_random_AI(active_player_index, player_col_state, choices, legal, random_key):
  '''An AI that makes all choices purely at random.'''
  #Input:
  #  active_player_index = An int with whose turn it currently is (which player the AI is playing for)
  #  player_col_state = An int array of size (N_players, 11) showing how many entries REMAINING until column is claimed for each player
  #  choices = An array of size (9,11) with the 9 possible choices available to the player
  #  legal = An array of size (9,) with whether or not each of the 9 choices are legal
  #  N_Col_To_Win, N_Max_Runners = Integers that can specify variants of the game rules 
  #Output: A tupl (choice_index, roll_again)
  #  1st entry: choice_index = An integer in [0,8] with which choice is to be played
  #             (Note, you must make sure the index you play is legal!)
  #  2nd entry: roll_again = A boolean on whether or not to roll again 
  
  #To get the unique choices you can do jnp.unique(choices[legal==True],axis=0)

  keys =  jrandom.split(random_key)
  
  random_scores = jnp.abs( jax.random.normal(keys[0], jnp.shape(legal)) )  
  choice_index = jnp.argmax(legal*random_scores,axis=0)  #Since all random_scores have the same distribution, this is a random legal choice

  random_scores = jax.random.normal(keys[1], (2,) )
  roll_again = jnp.argmax(random_scores,axis=0) #choose to roll again randomly!
  
  return choice_index, roll_again

@jit
def random_timid_AI(active_player_index, player_col_state, choices, legal, random_key):
  '''An AI that chooses what to choose (somewhat) randomly, and then is timid about rolling again or not'''

  #Inputs/Outputs same as for the pure_random_AI
  
  #Choose the choice randomly
  #Rolls again if it has <=2 runners and doesnt roll again if it has 3 runners already

  random_scores = jnp.abs( jax.random.normal(random_key, (9,) ) )  
  choice_index = jnp.argmax(legal*random_scores)  #Since all random_scores have the same distribution, this is a random legal choice

  N_runners = jnp.count_nonzero( choices[choice_index] )
  roll_again = (N_runners <= 2) 

  return choice_index, roll_again #silly AI picks the first choice and stops rolling again

@jit
def runner_weights_AI(active_player_index, player_col_state, choices, legal, random_key):
  '''An AI that uses the position of the runners to make choices, taking into account that some columns are better than others'''
  #Inputs/Ouputs same as other AIs

  column_weights = jnp.array([6,5,4,3,2,1,2,3,4,5,6]) #The weights used for each column
  reroll_threshold = 13.0 #Reroll if the score is lower than this, otherwise stay

  scores = (choices @ column_weights) #Calculate the score for each of the choices
  
  choice_index = jnp.argmax( legal*scores  ) #Choose the best one of the legal options 

  N_runners = jnp.count_nonzero( choices[choice_index] ) #Number of runners in our choice

  #Reroll if we have only 1 runner or if we are less than the reroll threshold
  roll_again =  jnp.logical_or(N_runners <= 1, scores[choice_index] < reroll_threshold) 

  return choice_index, roll_again

"""## Main game simulator code"""

def simulate_game(Player_AI, Verbose = False, N_PLAYERS=2, N_COL_TO_WIN=5, N_MAX_RUNNERS=3, PLAYER_COL_STATE_INIT=[3,5,7,9,11,13,11,9,7,5,3]):
  '''Run a simulation of the game Can't Stop!'''
  #Input:
  #   randome_key = jrandom key used for dice rolls
  #   Player_AI = List with the functions for player AIs
  #   Verbose = whether or not to print out a play-by-play of the game
  #Output:
  #  An array of shape (N_players,) with a 1 at the player who won
  
  #Initialize game state
  player_col_state = jnp.tile(jnp.array(PLAYER_COL_STATE_INIT,dtype=jnp.dtype('i1')),(N_PLAYERS, 1))
  
  #This flag tells us when the game is over
  game_in_progress = True
  
  #Choose a random player to start
  #  Note that the actual player who starts is one player later than the one chose here.
  active_player_index = random.randint(0,N_PLAYERS-1) 

  #Random key used for randomness
  random_key = jax.random.PRNGKey(int(time.time()))


  #Main loop that goes until someone wins the game
  
  turn_num = 0
  roll_num = 0
  while game_in_progress: #This will loop until the game ends 
    turn_num += 1
    #Update whose turn it is
    active_player_index = (active_player_index + 1) % N_PLAYERS
    
    if Verbose : print(f"Turn Number: {turn_num}")
    if Verbose : print(f"Player {active_player_index}:") 
    if Verbose : print("--Player Column State: \n", player_col_state)

    #Reset runners and "busted"/"roll again" flags that tell us the game state
    runner_col_state = jnp.zeros( 11 ,dtype=jnp.dtype('u1'))
    not_busted_state = True
    roll_again_state = True

    #Loop while player is chooising to rolling on their turn
    
    while roll_again_state:
      roll_num += 1
      #This represents a random dice roll 
      # (1296 = 6**4 is the number of possibilities for 4 6-sided dice)
      random_key, subkey_1, subkey_2 = jax.random.split(random_key, 3)
      dice_num =  int(jax.random.randint(subkey_1, (1,), 0,1296)) #random.randint(0,1295)

      if Verbose : print( f"----Roll #{roll_num}: {diceNum_to_diceRoll(dice_num)}")      
      
      #Generate all 9 possible runner choices and whether or not they are legal
      runner_choices, runner_legal = generate_all_choices_and_legality(dice_num,player_col_state,runner_col_state, N_MAX_RUNNERS)
      
      if Verbose : print("----Options:\n", jnp.unique(runner_choices[runner_legal==True],axis=0) ) 

      #Update the busted state: you are only not busted if you have at least one legal choice
      any_legal_choices = jnp.any(runner_legal)
      not_busted_state = not_busted_state and any_legal_choices
      if Verbose: print("---Busted? ", not not_busted_state)

      if not_busted_state:
        #Send the choices to the AI to choose from
        #Note that we run this even for ones where we've already busted (we just make sure to do nothing with this data in that case)
        active_player_AI = Player_AI[active_player_index]
        choice_index, roll_again_state = active_player_AI(active_player_index, player_col_state, runner_choices, runner_legal, subkey_2)

        #If you attempt to choose an illegal move, we count it the same as if you have busted!
        if runner_legal[choice_index] == False:
          not_busted_state = False  

        #Update the runner positions if you are not busted 
    
        runner_col_state = runner_choices[choice_index]
        
        if Verbose : print("----Runners chosen:\n", runner_col_state) 
        if Verbose :print(f"----Roll again choice: {roll_again_state}")
      
      #If you are busted you are not allowed to roll again! 
      roll_again_state = roll_again_state and not_busted_state
      

    #-----------------------
    #End of the players turn:
    #-----------------------

    #This resets your runners to zero if you had busted
    runner_col_state = runner_col_state*not_busted_state
    
    #Move the pieces according to the runner positions
    player_col_state = update_player_col_state(active_player_index,player_col_state,runner_col_state) 

    #Calculate columns claimed and check if game is over
    player_N_col_claimed = calculate_player_N_col_claimed(player_col_state)
    game_in_progress = not jnp.any(player_N_col_claimed >= N_COL_TO_WIN)

   
  #At the end of this loop, someone has won!
  if Verbose : 
    print("GAME OVER!") 
    print("Final board state:\n ", player_col_state)
    print("Final claimed column count: ", player_N_col_claimed)
    print("Winner: ", ( player_N_col_claimed >= N_COL_TO_WIN ))

  return ( player_N_col_claimed >= N_COL_TO_WIN )

#Play a bunch of games and record final result
def play_N_games(N_games, AIs, N_PLAYERS = 2):
  winners = jnp.zeros(N_PLAYERS,dtype=jnp.dtype('i4'))
  for i in range(N_games):
    if i % (N_games/10) == 0:
      print( int(100*(i / N_games)), "% done")
    winners += simulate_game(AIs)
  print("After ", N_games, " winners are ",winners)

"""## Tests

# Running multiple games at once

Running one game at a time is a bit too slow to be super useable for training, so here we set up a simulation that runners multiple games at the same time. This leads to a huge speedup! The AI program must be setup to input multiple states at once.

This is done by adding one dimension to all the arrays used in the game. For example, instead of "legal" being of shape (9,), it is now of shape (9,N_PARR) where N_PARR is the number of games being run in parallel.

## Making the AIs parralel

You can make the AI's play many games at once by using the JAX vmap function, which makes functions run over many things in a vector

### Option 1: Use VMAP to make the AI play parralel games
"""

#The input into an AI is: AI(active_player_index, player_col_state, choices, legal):
#We are using the last dimension as the parrelel one: this the #2 axis in player_col and choices and the #1 axis for legal. (The player index and random_keay are not parrelelized over)
# so we use vmap with in_axes=(None,2,2,1)
# out_axes=0 here because the output is normally a scalar.
random_timid_AI_vmap = jax.jit(jax.vmap( random_timid_AI, in_axes=(None,2,2,1,None), out_axes=0 ))
runner_weights_AI_vmap = jax.jit(jax.vmap( runner_weights_AI, in_axes=(None,2,2,1,None), out_axes=0 ))
pure_random_AI_vmap = jax.jit(jax.vmap( pure_random_AI, in_axes=(None,2,2,1,None), out_axes=0 ))

"""### Option 2: Write a vector version of the AI"""

#Note that the AIs that use randomness will use the same random seed for all their choices. Since we don't want this we can also program them manually if we want.

@jit
def pure_random_AI_parr(active_player_index, player_col_state, choices, legal, random_key):
  '''An AI that makes all choices purely at random.'''
  #Input:
  #  active_player_index = An int with whose turn it currently is (which player the AI is playing for)
  #  player_col_state = An int array of size (N_players, 11) showing how many entries REMAINING until column is claimed for each player
  #  choices = An array of size (9,11) with the 9 possible choices available to the player
  #  legal = An array of size (9,) with whether or not each of the 9 choices are legal
  #  N_Col_To_Win, N_Max_Runners = Integers that can specify variants of the game rules 
  #Output: A tupl (choice_index, roll_again)
  #  1st entry: choice_index = An integer in [0,8] with which choice is to be played
  #             (Note, you must make sure the index you play is legal!)
  #  2nd entry: roll_again = A boolean on whether or not to roll again 
  
  #To get the unique choices you can do jnp.unique(choices[legal==True],axis=0)

  keys =  jrandom.split(random_key)
  
  random_scores = jnp.abs( jax.random.normal(keys[0], jnp.shape(legal)) )  
  choice_index = jnp.argmax(legal*random_scores,axis=0)  #Since all random_scores have the same distribution, this is a random legal choice

  roll_again = jax.random.randint(keys[1], jnp.shape(choice_index), 0,2) #choose to roll again randomly!
  
  return choice_index, roll_again

@jit
def random_timid_AI_parr(active_player_index, player_col_state, choices, legal, random_key):
  '''An AI that chooses what to choose (somewhat) randomly, and then is timid about rolling again or not'''

  #Inputs/Outputs same as for the pure_random_AI
  
  #Choose the choice randomly
  #Rolls again if it has <=2 runners and doesnt roll again if it has 3 runners already

  random_scores = jnp.abs( jax.random.normal( random_key, jnp.shape(legal)) )  
  choice_index = jnp.argmax(legal*random_scores, axis = 0)  #Since all random_scores have the same distribution, this is a random legal choice

  N_PARR = jnp.shape(legal)[-1]

  my_choices = jnp.transpose(choices[choice_index,:,jnp.arange(N_PARR)],(1,0))

  N_runners = jnp.count_nonzero( my_choices, axis = 0)
  roll_again = (N_runners <= 2) 

  return choice_index, roll_again #silly AI picks the first choice and stops rolling again

#The pure AI parr cannot be parralelized by vmap because it uses non jax functions for randomness. To fix it is a bit annoying and you have to use Jax keys, and then write the parrelization by hand.

@jit
def random_true_index(key, bool_array):
  '''Given a boolean array and a jax random key, chooses an index of the array that has "True" in it'''
  return jrandom.choice(key, jnp.arange(jnp.shape(bool_array)[0]) , p= bool_array/jnp.sum(bool_array))

#This makes it so that randon_true index works for multidimensional arrays
random_true_index_by_rows = jax.vmap(random_true_index, in_axes = (None,0), out_axes=0)

@jit
def pure_random_AI_parr(active_player_index, player_col_state, choices, legal, random_key):
  '''A version of the pure random AI that works over N_PARR games at'''
  #Input:
  #  active_player_index = An int with whose turn it currently is (which player the AI is playing for)
  #  player_col_state = An int array of size (N_players, 11, N_PARR) showing how many entries REMAINING until column is claimed for each player
  #  choices = An array of size (9,11,N_PARR) with the 9 possible choices available to the player
  #  legal = An array of size (9,N_PARR) with whether or not each of the 9 choices are legal
  #   N_Col_To_Win, N_Max_Runners = Integers that can specify variants of the game rules 
  #Output: A tupl (choice_index, roll_again)
  #  1st entry: choice_index = An array of shape (N_PARR,) of integers in [0,8] with which choice is to be played
  #             (Note, you must make sure the index you play is legal!)
  #  2nd entry: roll_again = A boolean array of shape (N_PARR,) on whether or not to roll again

  
  #This chooses a random legal choice for each player by the following algorithm
  #Step 1. Choose a random positive score for each index 0 to 8
  #Step 2. Set all the illegal choices to have score 0 by multiplying by legal
  #Step 2. Return the largest score that is legal! 

  keys =  jrandom.split(random_key)
  
  random_scores = jnp.abs( jax.random.normal(keys[0], jnp.shape(legal)) )  
  choice_index = jnp.argmax(legal*random_scores,axis=0)  #Since all random_scores have the same distribution, this is a random legal choice

  roll_again = jrandom.randint(keys[1], jnp.shape(choice_index), 0,2) #choose to roll again randomly!
  
  return choice_index, roll_again #dummy AI picks the first choice and stops rolling again

"""## Making the game simulation parrallel"""

def simulate_game_parr(random_key,Player_AI, Verbose = False, Starting_Player=0, N_PARR=100, N_PLAYERS=2, N_COL_TO_WIN=5, N_MAX_RUNNERS=3, PLAYER_COL_STATE_INIT=[3,5,7,9,11,13,11,9,7,5,3]):
  '''Run a simulation of the game Can't Stop! running N_PARR games in parrallel'''
  #Note that the TURN order for all the games is the same, so who is the starting player matters! 

  #Input:
  #   random_key = A jax random key used to make all the dice rolls for the game
  #   Player_AI = List with the functions for player AIs
  #   Verbose = whether or not to print out a play-by-play of the game
  #Output:
  #  An array of shape (N_players,) with a 1 at the player who won
  
  #Initialize game state
  player_col_state = jnp.tile(jnp.array(PLAYER_COL_STATE_INIT,dtype=jnp.dtype('i1')),(N_PARR, N_PLAYERS, 1))
  player_col_state = jnp.transpose(player_col_state, (1,2,0)) #Move it so the N_PARR dimension is LAST
 
  
  #Record which games are in progress (to make sure we don't mess with those games)
  game_in_progress = jnp.ones(N_PARR, dtype=bool)
  
  #Note that the player whose turn it is the SAME accross all games
  #This means its improtant to run the function more than once so there is no bias towards whoever plays first
  active_player_index = Starting_Player - 1 
  
  #Main loop that goes until all games are over

  turn_num = 0
  roll_num = 0


  while jnp.any(game_in_progress): #This will loop until the game ends 
    turn_num += 1
    
    #Update whose turn it is
    active_player_index = (active_player_index + 1) % N_PLAYERS
    
    if Verbose : print("Player ",active_player_index,":") 
    #if Verbose : print("--Player Column State: \n",player_col_state)

    #Reset runners and "busted"/"roll again" flags
    runner_col_state = jnp.zeros( (11,N_PARR) ,dtype=jnp.dtype('u1'))

    #roll_again_state and not_busted_state keep track of whether or not the player has
    #chosen to roll again and/or busted yet 
    #This is vector of length N_PARR and is only true for games still in progress
    roll_again_state = game_in_progress
    not_busted_state = game_in_progress 


    #Loop while player is chooising to rolling on their turn
    while jnp.any( roll_again_state ):
      roll_num += 1

      #This represents a random dice roll for each N_PARR simulation 
      # (1296 = 6**4 is the number of possibilities for 4 6-sided dice)
      random_key, subkey_1, subkey_2 = jax.random.split(random_key,3)
      dice_num = jrandom.randint(subkey_1, (N_PARR,) , 0,1296)
      
      if Verbose : print("----DiceNums: ",dice_num) 

      
      #Generate all 9 possible runner choices and whether or not they are legal
      runner_choices, runner_legal = generate_all_choices_and_legality(dice_num,player_col_state,runner_col_state, N_MAX_RUNNERS)
      
      #Update the busted state: you are only not busted if you have at least one legal choice
      any_legal_choices = jnp.any(runner_legal==True,axis=0)

      #To stay in the game, you must be in the game already and have legal choices
      not_busted_state = jnp.logical_and(not_busted_state, any_legal_choices )

      
      
      #Send the choices to the AI to choose from
      #Note that we run this even for ones where we've already busted (we just make sure to do nothing with this data) 
      active_player_AI = Player_AI[active_player_index]
      
      choice_index, new_roll_again_state = active_player_AI(active_player_index, player_col_state, runner_choices, runner_legal, subkey_2)

      #Ensure the choice you made was legal. If you make an illegal choice we count it as if you busted.
      choice_was_legal = runner_legal[choice_index, jnp.arange(N_PARR)]
      not_busted_state = jnp.logical_and(not_busted_state, choice_was_legal )

      
      #Find the runner position if they would advance according to the choices, choosing choice_index[i] for simulation number i
      new_runner_col_state = jnp.transpose(runner_choices[choice_index,:,jnp.arange(N_PARR)], (1,0) )

      #Update the runners to these new positions only if you were still rolling!
      # If you don't meet this criteria, then your roll doesnt count and runners stay where they are
      runner_col_state = jnp.where( roll_again_state, new_runner_col_state, runner_col_state)
      
      #runner_col_state = jnp.where( jnp.logical_and(roll_again_state,not_busted_state), new_runner_col_state, runner_col_state)


      #Update roll_again_state for next round.
      #In order to roll_again next round, three things must all happend: 
      #1. You are not busted
      #2. You chose to roll again last time 
      #3. You chose to roll again this time 
      roll_again_state = jnp.logical_and( jnp.logical_and( not_busted_state,roll_again_state), new_roll_again_state) 
      
      
      if Verbose : print("----Roll Iteration: ", roll_num,"\n", "Busted_State: ",jnp.logical_not(not_busted_state),"Roll_Again_State: ",roll_again_state)
      
      
    
    #-----------------------
    #End of the players turn:
    #-----------------------
    
    #This line resets the runners of anyone who had busted to zero
    runner_col_state = runner_col_state * not_busted_state

    #Update the player positions!
    player_col_state = update_player_col_state(active_player_index,player_col_state,runner_col_state)
    
    if Verbose:
      [print(f"player_col_state Sim #{i} \n",player_col_state[:,:,i]) for i in range(N_PARR)]

    player_N_col_claimed = calculate_player_N_col_claimed(player_col_state)

    
    game_in_progress = jnp.logical_and( game_in_progress, jnp.all(player_N_col_claimed < N_COL_TO_WIN, axis=0))
    if Verbose: print(f"Turn # {turn_num}. Games in progress: {jnp.sum(game_in_progress)}")
   
  #At the end of this loop, one player has won!
  if Verbose : 
    print("GAME OVER!") 
    print(f"Number of rolls simulated {roll_num}")
    print(f"Final number of columns claimed \n {player_N_col_claimed}")
 
  return jnp.sum( player_N_col_claimed >= N_COL_TO_WIN , axis=1)

"""## Tests

Important: Keep in mind that the first AI is always going first here. If you want a "fair" test you have to run it twice, so each AI goes first half the time

# Ideas for a more complicated AI

The simple AI's here don't take into account the state of the board beyond the column locations. Therefore, they are not able to increase their level of risk in response to the possibility of losing the game. They also don't know how to "give up" on columns that the open is close to winning.

This AI estimates a value function which is supposed to represent the probability to win the game from a given state. Then using this, we can estimate the q function of the probability of winning by either rolling again or not. Then the maximum is chosen! This will allow it to take risks when it has a low probability of winning if the weights are chosen correctly!
"""