'''
This file tests functions from run_structcol.py.
'''

import infer_structcol
import numpy as np
from numpy.testing import assert_equal, assert_almost_equal
from infer_structcol.run_structcol import calc_refl_trans
from infer_structcol.main import Sample, Spectrum, find_close_indices
from .test_inference import ntrajectories, nevents, wavelength_sigma, sigma

def test_structcol_import():
    # Test that montecarlo.py is imported and Trajectory object is imported correctly
    from structcol import montecarlo as mc
    dummy_trajectory = mc.Trajectory("position", "direction", "weight")
    assert_equal(dummy_trajectory.position, "position")
    
def test_run_structcol():
    # Test that structcol package is imported and reflectance calculation is correct
    import structcol as sc

    wavelength = np.array([400., 500.]) 
    particle_radius = 150.
    thickness = 100.
    particle_index = np.array([1.40, 1.41]) 
    matrix_index = np.array([1.0, 1.0]) 
    volume_fraction = 0.5
    incident_angle = 0.0
    medium_index = np.array([1.0, 1.0]) 
    front_index = np.array([1.0, 1.0])
    back_index = np.array([1.0, 1.0]) 
    
    wavelength_ind = find_close_indices(wavelength_sigma, sc.Quantity(wavelength,'nm'))
    sigma_test = sigma[np.array(wavelength_ind)]
    
    refl, trans = calc_refl_trans(volume_fraction, particle_radius, thickness, 
                               Sample(wavelength, particle_index, matrix_index, medium_index, 
                                      front_index, back_index, incident_angle), ntrajectories, nevents, seed=1)
    spectrum = Spectrum(wavelength, reflectance = refl, transmittance = trans, 
                        sigma_r = sigma_test, sigma_t = sigma_test)
    
    outarray = np.array([0.84576,  0.74796])
    assert_almost_equal(spectrum.reflectance, outarray, decimal=5)
