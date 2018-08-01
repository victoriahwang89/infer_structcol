'''
This file contains the inference framework to estimate sample properties.
'''

import multiprocessing as mp
import numpy as np
import pandas as pd
import emcee
import lmfit
from .model import (calc_model_spect, calc_resid_spect, log_posterior)
from .run_structcol import calc_sigma

# define limits of validity for the MC scattering model. These values were 
# chosen such that they encompass the widest range of physically meaningful values
theta_range_default = {'min_particle_index':1.0, 'max_particle_index':3.0, 
                       'min_matrix_index':1.0, 'max_matrix_index':3.0,
                       'min_phi':0.35, 'max_phi':0.7, 'min_radius':80., 
                       'max_radius': 150., 'min_thickness':10., 'max_thickness':200., 
                       'min_l0_r':0, 'max_l0_r':1, 'min_l1_r':-1, 'max_l1_r':1,
                       'min_l0_t':0, 'max_l0_t':1, 'min_l1_t':-1, 'max_l1_t':1}  # radius in nm, thickness in um
                       
# define initial guesses for theta in case the user doesn't give an initial guess. 
# These values were arbitrarily chosen. It is highly recommended that the user
# passes a good initial guess based on their knowledge of the system. 
theta_guess_default = {'particle_index':1.5, 'matrix_index':1.0, 'phi':0.568, 'radius':104, 'thickness':62, 
                       'l0_r':0.02, 'l1_r':0, 'l0_t':0.02, 'l1_t':0}  # radius in nm, thickness in um

def find_max_like(data, sample, theta_guess, theta_range, sigma, ntrajectories, nevents, losses, seed=None):
    '''
    Uses lmfit to approximate the highest likelihood parameter values.
    We use likelihood instead of posterior because lmfit requires an array of 
    residuals.

    Parameters
    ----------
    data: Spectrum object
        experimental dataset
    sample: Sample object
        information about the sample that produced data_spectrum
    theta_guess: dictionary 
        best guess of the expected parameter values (particle_index, matrix_index, 
        phi, radius, thickness, l0_r, l1_r, l0_t, l1_t)
    theta_range: dictionary
        expected ranges of the parameter values 
        (min_particle_index, max_particle_index, min_matrix_index, max_matrix_index,
        min_phi, max_phi, min_radius, max_radius, min_thickness, max_thickness, 
        min_l0_r, max_l0_r, min_l1_r, max_l1_r, min_l0_t, max_l0_t, min_l1_t, max_l1_t) 
    sigma: 2-tuple
        uncertainties (taken to be 1 standard deviation) of the multiple scattering
        calculations (reflectance sigma, transmittance sigma).
    ntrajectories: int
        number of trajectories for the multiple scattering calculations
    nevents: int
        number of scattering events for the multiple scattering calculations
    seed: int (optional)
        if specified, passes the seed through to the MC multiple scattering 
        calculation    
        
    Returns
    -------
    theta: 7 or 9-tuple
        best fit (particle_index, matrix_index, phi, radius, thickness, l0, l1) 
        or (particle_index, matrix_index, phi, radius, thickness, 
        l0_r, l1_r, l0_t, l1_t) as floats
    '''
    # define a function that takes in a dictionary of the initial theta and 
    # calculates the residuals to be minimized 
    def resid(params):
        theta = []
        for key in sorted(params):
            theta.append(params[key])
            
        # make the theta into a tuple
        theta = tuple(theta)

        theory_spect = calc_model_spect(sample, theta, sigma, ntrajectories, nevents, losses, seed)
        resid_spect = calc_resid_spect(data, theory_spect)
        residual = np.concatenate([resid_spect.reflectance/resid_spect.sigma_r, 
                                   resid_spect.transmittance/resid_spect.sigma_t])
        
        return residual[np.isfinite(residual)]#.view(np.float)
    
    fit_params = lmfit.Parameters()
    for key in sorted(theta_guess):
        fit_params[key] = lmfit.Parameter(value=theta_guess[key], min=theta_range['min_'+key], max=theta_range['max_'+key])

    fit_params = lmfit.minimize(resid, fit_params, epsfcn=0.2, xtol=1e-20, ftol=1e-20).params
    #fit_params = lmfit.minimize(resid, fit_params).params
    
    return tuple(fit_params.valuesdict().values())


def run_mcmc(data, sample, nwalkers, nsteps, theta_guess = theta_guess_default, 
             theta_range = theta_range_default, ntrajectories=600, nevents=200, losses=False, seed=None):
    '''
    Performs actual mcmc calculation. Returns an Emcee Sampler object. 

    Parameters
    ----------
    data: Spectrum object
        experimental dataset
    sample: Sample object
        information about the sample that produced data_spectrum
    nwalkers: int (even)
        number of parallelized MCMC walkers to use
    nsteps: int
        number of steps taken by each walker
    theta_guess: dictionary (optional)
        user's best guess of the expected parameter values (particle_index, 
        matrix_index, phi, radius, thickness)
    theta_range: dictionary (optional)
        user's best guess of the expected ranges of the parameter values 
        (min_particle_index, max_particle_index, min_matrix_index, max_matrix_index, 
        min_phi, max_phi, min_radius, max_radius, min_thickness, max_thickness) 
    ntrajectories: int
        number of trajectories for the multiple scattering calculations
    nevents: int
        number of scattering events for the multiple scattering calculations
    seed: int (optional)
        sets the seed for all MC scattering trajectory chains. 
        DOES NOT set the seed for MCMC walkers.
    '''    

    # set expected ranges of values to initialize walkers. If the user inputs an incorrect key, then raise an Error
    for key in theta_range:
        if key not in theta_range_default:
            raise KeyError('Parameter {0} in theta_range is not defined correctly'.format(str(key)))
    theta_range_default.update(theta_range) 
    
    # set initial guesses to initialize walkers. If the user inputs an incorrect key, then raise an Error
    for key in theta_guess:
        if key not in theta_guess_default:
            raise KeyError('Parameter {0} in theta_guess is not defined correctly'.format(str(key)))
    theta_guess_default.update(theta_guess) 
    
    
#    theta_TF = []
#    for key in sorted(theta_guess_default):        # sort the keys in alphabetic order to ensure the same answer
#        theta_TF.append(key in theta_guess.keys()) # across versions of python

                        
    # update the theta_guess and theta_range dictionaries depending on whether
    # the user inputs reflectance and/or transmittance data
    guess_keylist = ['particle_index', 'matrix_index', 'phi', 'radius', 'thickness']
    if losses == True:
        if 'reflectance' in data.keys():
            guess_keylist = guess_keylist + ['l0_r', 'l1_r']
        if 'transmittance' in data.keys():
            guess_keylist = guess_keylist + ['l0_t', 'l1_t']
    min_range_keylist = ['min_'+key for key in guess_keylist]
    max_range_keylist = ['max_'+key for key in guess_keylist]
    range_keylist = [None]*(len(min_range_keylist) + len(max_range_keylist))
    range_keylist[::2] = min_range_keylist
    range_keylist[1::2] = max_range_keylist
    
    theta_guess = {key:theta_guess_default[key] for key in guess_keylist}
    theta_range = {key:theta_range_default[key] for key in range_keylist}

    # Calculate the standard deviation of the multiple scattering calculations
    # based on number of trajectories and number of scattering events
    sigma = calc_sigma(theta_guess['particle_index'], theta_guess['matrix_index'], 
                       theta_guess['phi'], theta_guess['radius'], theta_guess['thickness'], 
                       sample, ntrajectories, nevents, plot=False, seed=seed)

    theta = find_max_like(data, sample, theta_guess, theta_range, sigma, ntrajectories, nevents, losses, seed)
    ndim = len(theta)

    # set walkers in a distribution with width .05
    particle_index = np.clip(theta[0]*np.ones(nwalkers) + 0.1*np.random.randn(nwalkers), 
                 theta_range['min_particle_index'], theta_range['max_particle_index'])
    matrix_index = np.clip(theta[1]*np.ones(nwalkers) + 0.1*np.random.randn(nwalkers), 
                 theta_range['min_matrix_index'], theta_range['max_matrix_index'])
    vf = np.clip(theta[2]*np.ones(nwalkers) + 0.01*np.random.randn(nwalkers), 
                 theta_range['min_phi'], theta_range['max_phi'])
    radius = np.clip(theta[3]*np.ones(nwalkers) + 1*np.random.randn(nwalkers), 
                 theta_range['min_radius'], theta_range['max_radius'])
    thickness = np.clip(theta[4]*np.ones(nwalkers) + 1*np.random.randn(nwalkers), 
                 theta_range['min_thickness'], theta_range['max_thickness'])
    
    if losses == True:
        # Clip the distributions such that there are no walkers out of prior ranges.
        # The limits for l0_r and l1_r are fixed and the same as for l0_t and l1_t, 
        # so we can use the default values directly
        l0 = np.clip(theta[5]*np.ones(nwalkers) + 0.01*np.random.randn(nwalkers), 
                 theta_range_default['min_l0_r'], theta_range_default['max_l0_r'])
        # clip the sum of l0 and l1 and subtract l0 to ensure that the clipped 
        # l1 satisfies 0 < l0 + l1 < 1        
        l1 = np.clip((theta[5] + theta[6]) * np.ones(nwalkers) + 
                  0.01*np.random.randn(nwalkers), theta_range_default['min_l1_r'], theta_range_default['max_l1_r']) - l0
                         
        if ndim == 7:
            theta = np.vstack((particle_index,matrix_index,vf,radius,thickness,l0,l1)).T.tolist()
            
        if ndim == 9:
            l0_1 = np.clip(theta[7] * np.ones(nwalkers) + 
                       0.01*np.random.randn(nwalkers), theta_range_default['min_l0_r'], theta_range_default['max_l0_r'])
            l1_1 = np.clip((theta[7] + theta[8]) * np.ones(nwalkers) + 
                       0.01*np.random.randn(nwalkers), theta_range_default['min_l1_r'], theta_range_default['max_l1_r']) - l0_1
            theta = np.vstack((particle_index,matrix_index,vf,radius,thickness,l0,l1,l0_1,l1_1)).T.tolist()
    else: 
        theta = np.vstack((particle_index,matrix_index,vf,radius,thickness)).T.tolist()
        
    # figure out how many threads to use
    nthreads = np.min([nwalkers, mp.cpu_count()])

    sampler = emcee.EnsembleSampler(nwalkers, ndim, log_posterior, 
                                    args=[data, sample, theta_range, sigma,
                                          ntrajectories, nevents, losses, seed], threads=nthreads)                                     
    sampler.run_mcmc(theta, nsteps)

    return sampler
    

def run_mcmc_without_inference(data, sample, theta_guess, theta_range, 
                               ntrajectories=600, nevents=200, losses=False, seed=None):
    '''
    Performs actual mcmc calculation. Returns an Emcee Sampler object. 

    Parameters
    ----------
    data: Spectrum object
        experimental dataset
    sample: Sample object
        information about the sample that produced data_spectrum
    theta_guess: dictionary (optional)
        user's best guess of the expected parameter values (particle_index, 
        matrix_index, phi, radius, thickness)
    theta_range: dictionary (optional)
        user's best guess of the expected ranges of the parameter values 
        (min_particle_index, max_particle_index, min_matrix_index, max_matrix_index, 
        min_phi, max_phi, min_radius, max_radius, min_thickness, max_thickness) 
    ntrajectories: int
        number of trajectories for the multiple scattering calculations
    nevents: int
        number of scattering events for the multiple scattering calculations
    seed: int (optional)
        sets the seed for all MC scattering trajectory chains. 
        DOES NOT set the seed for MCMC walkers.
    '''    

    # set expected ranges of values to initialize walkers. If the user inputs an incorrect key, then raise an Error
    for key in theta_range:
        if key not in theta_range_default:
            raise KeyError('Parameter {0} in theta_range is not defined correctly'.format(str(key)))
    theta_range_default.update(theta_range) 
    
    # set initial guesses to initialize walkers. If the user inputs an incorrect key, then raise an Error
    for key in theta_guess:
        if key not in theta_guess_default:
            raise KeyError('Parameter {0} in theta_guess is not defined correctly'.format(str(key)))
    theta_guess_default.update(theta_guess) 
           
    # update the theta_guess and theta_range dictionaries depending on whether
    # the user inputs reflectance and/or transmittance data
    guess_keylist = ['particle_index', 'matrix_index', 'phi', 'radius', 'thickness']
    if losses == True:
        if 'reflectance' in data.keys():
            guess_keylist = guess_keylist + ['l0_r', 'l1_r']
        if 'transmittance' in data.keys():
            guess_keylist = guess_keylist + ['l0_t', 'l1_t']
    min_range_keylist = ['min_'+key for key in guess_keylist]
    max_range_keylist = ['max_'+key for key in guess_keylist]
    range_keylist = [None]*(len(min_range_keylist) + len(max_range_keylist))
    range_keylist[::2] = min_range_keylist
    range_keylist[1::2] = max_range_keylist
    
    theta_guess = {key:theta_guess_default[key] for key in guess_keylist}
    theta_range = {key:theta_range_default[key] for key in range_keylist}

    # Calculate the standard deviation of the multiple scattering calculations
    # based on number of trajectories and number of scattering events
    sigma = calc_sigma(theta_guess['particle_index'], theta_guess['matrix_index'], 
                       theta_guess['phi'], theta_guess['radius'], theta_guess['thickness'], 
                       sample, ntrajectories, nevents, plot=False, seed=seed)
   
    theta = find_max_like(data, sample, theta_guess, theta_range, sigma, ntrajectories, nevents, losses, seed)

    return theta
    