# -*- coding: utf-8 -*-
"""
Created on Wed Feb 21 14:29:50 2024

@author: zgl12 + cha227 
"""

import numpy as np
from numbers import Number
from math import exp, floor, log, pi, sqrt
from scipy import integrate,optimize
import matplotlib.pyplot as plt
from scipy.optimize import fsolve, root_scalar

#from astropy.cosmology._utils import aszarr
# from . import units as cu
from astropy.cosmology import units as cu
from astropy import units as u
from astropy.units import Quantity
import astropy.constants as const

############################################################################################################
# Unit Conversions and Constants

_H0units_to_invs = (u.km / (u.s * u.Mpc)).to(1.0 / u.s)
_sec_to_Gyr = u.s.to(u.Gyr)
# const in critical density in cgs units (g cm^-3)
_critdens_const = (3 / (8 * pi * const.G)).cgs.value
# angle conversions
_radian_in_arcsec = (1 * u.rad).to(u.arcsec)
_radian_in_arcmin = (1 * u.rad).to(u.arcmin)
# Radiation parameter over c^2 in cgs (g cm^-3 K^-4)
_a_B_c2 = (4 * const.sigma_sb / const.c**3).cgs.value
# Boltzmann constant in eV / K
_kB_evK = const.k_B.to(u.eV / u.K)


############################################################################################################

def aszarr(z):
    """Redshift as a `~numbers.Number` or |ndarray| / |Quantity| / |Column|.

    Allows for any ndarray ducktype by checking for attribute "shape".
    """
    if isinstance(z, (Number, np.generic)):  # scalars
        return z
    elif hasattr(z, "shape"):  # ducktypes NumPy array
        if getattr(z, "__module__", "").startswith("pandas"):
            # See https://github.com/astropy/astropy/issues/15576. Pandas does not play
            # well with others and will ignore unit-ful calculations so we need to
            # convert to it's underlying value.
            z = z.values
        if hasattr(z, "unit"):  # Quantity Column
            return (z << cu.redshift).value  # for speed only use enabled equivs
        return z
    # not one of the preferred types: Number / array ducktype
    return Quantity(z, cu.redshift).value

class timescape:
    def __init__(self, fv0 = 0.695, H0 = 61.7, H0_type = 'dressed', T0 = 2.725 * u.K):
        '''
        Parameters
        ----------
        fv0 : Float
            Void Fraction at present time.
        
        H0 : Float
            Dressed Hubble Parameter at present time.
        '''

        #Void Fraction at Present Time
        self.fv0 = fv0 

        if H0_type.lower() == 'bare':
            self.H0_bare = H0 * u.km / (u.s * u.Mpc)
            self.H0_dressed = (4*self.fv0**2 + self.fv0 + 4) * self.H0_bare / (2 * (2 + self.fv0)) #* u.km / (u.s * u.Mpc)
            if isinstance(T0, u.Quantity):
                self.T0_bare = T0
                self.T0_dressed = self.T0_bare*self._lapse_function(0)
            else:
                self.T0_bare = T0 * u.K
                self.T0_dressed = T0 * self._lapse_function(0)
        elif H0_type.lower() == 'dressed':
            self.H0_dressed = H0 * u.km / (u.s * u.Mpc)
            self.H0_bare = (2 * (2 + self.fv0) * self.H0_dressed) / (4*self.fv0**2 + self.fv0 + 4) #* u.km / (u.s * u.Mpc)
            if isinstance(T0, u.Quantity):
                self.T0_dressed = T0
                self.T0_bare = T0/self._lapse_function(0)
            else:
                self.T0_dressed = T0 * u.K
                self.T0_bare = T0 / self._lapse_function(0)
        else:
            raise ValueError("H0_type must be either 'bare' or 'dressed'")

        #Present Bare Density Parameters
        self.Om0_bare = self.Om_bare(0)
        self.Ok0_bare = self.Ok_bare(0)
        self.OQ0_bare = self.OQ_bare(0)

        #Present Dressed Density Parameters
        self.Om0_dressed = self.Om0_bare * self._lapse_function(0)**3
        self.Ok0_dressed = self.Ok0_bare * self._lapse_function(0)**3
        self.OQ0_dressed = self.OQ0_bare * self._lapse_function(0)**3
        

        self.b = (2. * (1. - self.fv0)*(2. + self.fv0)) / (9. * self.fv0 * self.H0_bare.value)  # b parameter
        self.t0 = self.volume_average_time(0)

        if H0_type.lower() == 'bare':
            self.age = self.t0
            self.T0 = self.T0_bare
        elif H0_type.lower() == 'dressed':
            self.age = self.wall_time(0)
            self.T0 = self.T0_dressed

    #Energy densities for dressed and bare parameters
    def Om_bare(self, z):
        return 4* (1 - self.fv(z)) / (2 + self.fv(z))**2 # Eq. B3 Average observational quantities in the timescape cosmology

    def Ok_bare(self, z):
        return 9 * self.fv(z) / (2 + self.fv(z))**2 # Eq. B4 Average observational quantities in the timescape cosmology
    
    def OQ_bare(self, z):
        return -self.fv(z) * (1 - self.fv(z))  / (2 + self.fv(z))**2 # Eq. B5 Average observational quantities in the timescape cosmology
    
    def Om_dressed(self, z):
        return self.Om_bare(z) * self._lapse_function(z)**3
    
    def Ok_dressed(self, z):
        return self.Ok_bare(z) * self._lapse_function(z)**3

    def OQ_dressed(self, z):
        return self.OQ_bare(z) * self._lapse_function(z)**3

    def _lapse_function(self, z):
        return 0.5*(2 + self.fv(z)) # Eq. B7 Average observational quantities in the timescape cosmology

    def z1(self, t):
      '''
      Parameters
      ----------
      t : float
        Time in Hubble years.

      Returns
      -------
      Float
          The cosmological redshift function for the time. 
      '''
      fv = self.fv(t, tmode = True)

      return (2+fv)*fv**(1/3) / ( 3*t* self.H0_bare.value*self.fv0**(1/3) ) # Eq. 38 Average observational quantities in the timescape cosmology

    # Define the _texer function
    def _tex(self, z):
        '''
        Parameters
        ----------
        z : array of floats
            CMB Redshift.

        Returns
        -------
        Float
            Time 
        '''
        # # Define the function to find the root
        # def func(t):
        #     return self.z1(t) - z - 1
        # #   Use root_scalar to find the root
        # result = root_scalar(func, bracket=[0.0001, 1])  # Adjust the bracket if needed
        # return result.root

        # Define the function to find the root
        def func(t, z):
            return self.z1(t) - z - 1

        # Vectorize the function
        vfunc = np.vectorize(func)

        # Use root_scalar to find the root
        def find_root(z):
            return root_scalar(lambda t: vfunc(t, z), bracket=[0.0001, 1]).root  # Adjust the bracket if needed

        # Vectorize the root finding function
        vfind_root = np.vectorize(find_root)

        return vfind_root(z)



    def wall_time(self, zs):
        '''
        Parameters
        ----------
        zs : Array of floats
            Redshifts in the CMB frame.

        Returns
        -------
        astropy quantity
            Gives the age of the universe at a given redshift for a wall observer.
        '''
        zs = aszarr(zs)
        t = self._tex(zs) / _H0units_to_invs * _sec_to_Gyr
        term1 = 2.0 *t /3.0
        term2 = 4.0 * self.Om0_dressed/(27.0 * self.fv0 * self.H0_bare.value * _H0units_to_invs / _sec_to_Gyr)
        term3 = np.log(1.0 + (9.0 * self.fv0 * self.H0_bare.value * _H0units_to_invs * t / _sec_to_Gyr) / (4.0 * self.Om0_dressed))
        tau = term1 + term2 * term3

        return Quantity(tau, unit=u.Gyr)
  
    
    def lookback_time(self, zs):
        '''
        Parameters
        ----------
        zs : Float
            Redshift in CMB frame.

        Returns
        -------
        astropy quantity
            Gives the lookback time at a given redshift. Same as wall_time.

        '''

        return self.wall_time(zs)
    
    def lookback_distance(self, zs):
        '''
        Parameters
        ----------
        zs : Array of floats
            Redshift in CMB frame.

        Returns
        -------
        astropy quantity
            Gives the lookback distance at a given redshift. Same as luminosity distance.

        '''

        return self.luminosity_distance(zs)
    
    def volume_average_time(self, zs):
        '''
        Parameters
        ----------
        zs : Array of floats
            Redshift in CMB frame.

        Returns
        -------
        astropy quantity
            Gives the volume average age of the universe at a given redshift.
        '''
        zs = aszarr(zs)

        t = self._tex(zs) / _H0units_to_invs * _sec_to_Gyr
        return Quantity(t, unit=u.Gyr)

    def _yin(self,yy):
        yin = ((2 * yy) + (self.b / 6) * (np.log(((yy + self.b) ** 2) / ((yy ** 2) + (self.b ** 2) - yy * self.b)))
            + ((self.b / (3 ** 0.5)) * np.arctan((2 * yy - self.b) / ((3 ** 0.5) * self.b))))
        return yin

    def fv(self, z, tmode = False):
        '''
        Parameters
        ----------
        z : Float
            Redshift in CMB frame.
        t : Bool
            If True, returns the time instead of the redshift

        Returns
        -------
        Float
            Tracker soln as function of time.
        '''

        if tmode:
            t = z
            x = 3 * self.fv0 * t * self.H0_bare.value
            return x /(x + (1.-self.fv0)*(2.+self.fv0)) # Eq. B2 Average observational quantities in the timescape cosmology
        else:
            t = self._tex(z)
            x = 3 * self.fv0 * t * self.H0_bare.value
            return x /(x + (1.-self.fv0)*(2.+self.fv0)) # Eq. B2 Average observational quantities in the timescape cosmology

    def H_bare(self, zs):
        '''
        Parameters
        ----------
        z : Array of floats
            Redshift in CMB frame.

        Returns
        -------
        Float
            Bare Hubble Parameter.
        '''
        zs = aszarr(zs)
        t = self._tex(zs) # Time
        hb = ( (2 + self.fv(zs) ) / ( 3*t ) ) # Eq. B6 Average observational quantities in the timescape cosmology
        return Quantity(hb, unit=u.km / (u.s * u.Mpc) )

    def H_dressed(self, zs):
        '''
        Parameters
        ----------
        zs : Array of floats
            Redshift in CMB frame.
 
        Returns
        -------
        Float
            Dressed Hubble Parameter.
        '''
       
        zs = aszarr(zs)
        t = self._tex(zs)
        hd = ( 4*self.fv(zs)**2 + self.fv(zs) +4 ) / ( 6*t ) # Eq. B8 Average observational quantities in the timescape cosmology
        return Quantity(hd, unit=u.km / (u.s * u.Mpc) )

    def q_bare(self, zs):
        '''
        Parameters
        ----------
        z : Array of floats
            Redshift in CMB frame.

        Returns
        -------
        Float
            Bare Deceleration Parameter.
        '''

        zs = aszarr(zs)
        qb = 2 * (1 - self.fv(zs))**2 / (2 + self.fv(zs))**2 # Eq. 58 ArXiv: 1311.3787
        return qb
    
    def q_dressed(self, zs):
        '''
        Parameters
        ----------
        z : Array of floats
            CMB Redshift.

        Returns
        -------
        Array of floats
            Dressed Deceleration Parameter.
        ''' 
        
        zs = aszarr(zs)
        numerator = - (1 - self.fv(zs)) * (8*self.fv(zs)**3 + 39*self.fv(zs)**2 - 12*self.fv(zs) - 8)
        denominator = (4 + 4*self.fv(zs)**2 + self.fv(zs))**2
        return numerator/denominator

    def scale_factor_bare(self,z):
        '''
        Parameters
        ----------
        z : Array of floats
            Redshift in CMB frame.
        
        Returns
        -------
            Bare Scale Factor (setting a_dressed(0) = 1).
        '''
        t = self._tex(z)
        prefactor = self._lapse_function(0) * (3*self.H0_bare.value*t)**(2/3) / (2 + self.fv0)
        term1 = (3*self.fv0*self.H0_bare.value*t  +  (1-self.fv0)*(2+self.fv0))**(1/3)
        a_bare = prefactor * term1
        return a_bare
    
    def scale_factor_dressed(self,z):
        '''
        Parameters
        ----------
        z : Array of floats
            Redshift in CMB frame.
        
        Returns
        -------
            Dressed Scale Factor (setting a_dressed(0) = 1).
        '''
        a_dressed = (self.scale_factor_bare(z) * self._lapse_function(0)) / (self.scale_factor_bare(0) * self._lapse_function(z))
        return a_dressed

    def _F(self, z):

        '''
        Parameters
        ----------
        z : Array of floats
            Redshift in CMB frame.

        Returns
        -------
        Float
            F function 
            Eqn.41 Average observational quantities in the timescape cosmology
        '''
        t = self._tex(z)
        term1 = 2.*t**(1/3.)
        term2 = (self.b**(1/3.) /6.)*np.log( (t**(1/3.) + self.b**(1/3.))**2 / (-self.b**(1/3.)*t**(1/3.) + self.b**(2/3.) + t**(2/3.)) )
        term3 = (self.b**(1/3.)/np.sqrt(3)) * np.arctan( (2*t**(1/3.) - self.b**(1/3.)) / (np.sqrt(3) * self.b**(1/3.)) )
        return term1 + term2 + term3
        
    def _ordering(self, z_1_temp, z_2_temp):

        if isinstance(z_1_temp, (np.ndarray, list)) & isinstance(z_2_temp, (np.ndarray, list)):
            if (len(z_1_temp) == len(z_2_temp)) | (len(z_1_temp) == 1) | (len(z_2_temp) == 1):
                z_1, z_2 = self._order_output(z_1_temp, z_2_temp)
                return z_1, z_2
            else:
                raise ValueError("Input lengths are expected to coincide or one of them is expected to be of length 1.")
        elif isinstance(z_1_temp, (int, float)) | isinstance(z_2_temp, (int, float)):
            z_1, z_2 = self._order_output([z_1_temp], [z_2_temp])
            return z_1, z_2
        else:
            raise ValueError("Input lengths are expected to coincide or one of them is expected to be of length 1.")

    def _order_output(self, z_1_temp, z_2_temp, verbose = True):
            z_1 = np.minimum(z_1_temp, z_2_temp)  # Take the lower values
            z_2 = np.maximum(z_1_temp, z_2_temp)  # Take the higher values
            if not np.array_equal(z_1, z_1_temp) & verbose:
                print("Reordering inputs to make z_1 < z_2.")

            # Find indices where z_1 and z_2 are different
            indices = np.where(z_1 != z_2)

            # Filter z_1 and z_2 using the indices
            z_1 = z_1[indices]
            z_2 = z_2[indices]
            return z_1, z_2

    def angular_diameter_distance(self, z_2, z_1 =0): 
        '''
        Parameters
        ----------
        zs : Array of floats
            Redshift in CMB frame.
        z_2 : Array of floats
            Redshift in CMB frame.

        Returns
        -------
        distances: Float
            Angular Diameter Distance.
        '''

        z_1 = aszarr(z_1)
        z_2 = aszarr(z_2)
        z_1, z_2 = self._ordering(z_1, z_2)
        t = self._tex(z_2)

        if isinstance(z_2, (int, float)):
            distance = (const.c.to('km/s').value * t**(2/3.) * (self._F(z_1) - self._F(z_2)) ) 
            return Quantity(distance, unit=u.Mpc)
        elif len(z_2) == len(z_1):
            distance = (const.c.to('km/s').value * t**(2/3.) * (self._F(z_1) - self._F(z_2)) ) 
            return Quantity(distance, unit=u.Mpc)
        elif len(z_2) == 1:
            distance = (const.c.to('km/s').value * t**(2/3.) * (self._F(z_1) - self._F(z_2[0])) ) 
            return Quantity(distance, unit=u.Mpc)
        elif len(z_1) == 1:
            distance = (const.c.to('km/s').value * t**(2/3.) * (self._F(z_1[0]) - self._F(z_2)) ) 
            return Quantity(distance, unit=u.Mpc)
        else:
            raise ValueError("Input redshifts must be the same length")
    
    def angular_diameter_distance_z1z2(self, z_1, z_2):
        '''
        Parameters
        ----------
        z_1: Array of floats
            Redshift in CMB frame
        z_2: Array of Floats
            Redshift in CMB frame

        Where z_2 > z_1.
        Returns
        -------
        distances: Float
            Angular Diameter Distance between z_1 and z_2.
        '''

        return self.angular_diameter_distance(z_1, z_2)
    
    def transverse_comoving_distance(self, zs, z_2 = 0):
        '''
        Parameters
        ----------
        zs : Array of floats
            Redshift in CMB Frame.

        Returns
        -------
        distances: Float
            Transverse Comoving Distance.
        '''

        zs = aszarr(zs)

        dist = self.angular_diameter_distance(zs, z_2) * (1+zs)
        return Quantity(dist, unit=u.Mpc )
    
    def luminosity_distance(self, zs, z_2  = 0):
        '''
        Parameters
        ----------
        zs : Array of floats
            Redshift in CMB Frame.

        Returns
        -------
        distances: Float
            Luminosity Distance.
        '''
        
        zs = aszarr(zs)

        dist = self.angular_diameter_distance(zs, z_2) * (1+zs)**2
        return Quantity(dist, unit=u.Mpc)

if __name__ == '__main__':
    H0 = 61.7 # dressed H0 value
    fv0 = 0.695 # Void Fraction at present time
    ts = timescape(fv0=fv0, H0=H0) # Initialise TS class
    
    print("test distance = ", ts.angular_diameter_distance([3], [1]))
    print("test distance = ", ts.angular_diameter_distance([1], [3]))
    print("test distance = ", ts.angular_diameter_distance([1,2], [3]))
    print("test distance = ", ts.angular_diameter_distance([1], [3,2]))
    
   

 
