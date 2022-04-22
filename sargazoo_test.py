#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Mon Apr  4 17:44:46 2022

@author: ???
"""

import os
import sys
import yaml
import argparse
import datetime as dt
import netCDF4 as nc
import xarray as xr
import numpy as np
from datetime import datetime, timedelta
# from opendrift.readers import reader_basemap_landmask
from opendrift.readers import reader_netCDF_CF_generic
from opendrift.readers import reader_ROMS_native
from opendrift.readers import reader_NEMO_native
from opendrift.models.oceandrift import OceanDrift

from siphon.catalog import TDSCatalog
from subprocess import Popen
from opendrift.readers.basereader import BaseReader as br



def getSafeOutputFilename(proposedFilename, fextension, count=0):
    if os.path.exists(proposedFilename + '.' + fextension):
        if proposedFilename.split('_')[-1].isnumeric():
            count = int(proposedFilename.split('_')[-1])
            proposedFilename = '_'.join(proposedFilename.split('_')[0:-1])
        nproposedFilename = proposedFilename + '_' + str(count+1)
        return getSafeOutputFilename(nproposedFilename, fextension, count+1)
    else:
        return proposedFilename + '.' + fextension



if __name__ == "__main__":

  parser = argparse.ArgumentParser(description='Run far field model OPENDRIFT', prog='run_farfield')
  parser.add_argument('--subset', '-s', action='store', dest='PtoParam', help='yaml file with the information about point.')
  parser.add_argument('--commands', '-c', action='store_true', dest='show_commands', help='Just show the commands to run')

  # args = parser.parse_args('--config-file', "../Pto_Config.yaml")
  args = parser.parse_args()
  # TODO Add verbose mode
  if args.PtoParam:
      with open(args.PtoParam, 'r') as stream:
          try: 
              PtoParam = yaml.safe_load(stream)
          except:
              print ('Something went wrong reading ' + args.subsetconfig)            

  # IF date is NOT given, run the present day
  if PtoParam['sim']['StarTime'] == None:
      # starttime = (dt.datetime.today() - dt.timedelta(days=1)).strftime("%Y%m%d")
      # endtime = (dt.datetime.today() + dt.timedelta(days=PtoParam['cicoil']['sim_len'])).strftime("%Y%m%d")
      starttime = (dt.datetime.today().replace(microsecond=0, second=0, minute=0, hour=0) - dt.timedelta(days=1))
      endtime = (dt.datetime.today().replace(microsecond=0, second=0, minute=0, hour=0) + dt.timedelta(days=PtoParam['cicoil']['sim_len']))
  else:
      # smonth = int(PtoParam['sim']['Smonth'] + 1)
      starttime = dt.datetime(int(PtoParam['sim']['StarTime'][0:4]), int(PtoParam['sim']['StarTime'][4:6]), int(PtoParam['sim']['StarTime'][6:8]),
                              PtoParam['sim']['Shour'], 0)

      # emonth = int(PtoParam['sim']['Emonth'] + 1)
      endtime = dt.datetime(int(PtoParam['sim']['EndTime'][0:4]), int(PtoParam['sim']['EndTime'][4:6]), int(PtoParam['sim']['EndTime'][6:8]),
                            PtoParam['sim']['Ehour'], 0)

  # if PtoParam['cicoil']['wind_factor'] != None:
  #     wind_factor = float(PtoParam['cicoil']['wind_factor'])
  # else: wind_factor = 0.035
  
  # Select Simulation location and results output file
  output_path = os.path.join(PtoParam['outdir'],PtoParam['point']['name'])
  # TAMOC output dir
  txtTime = starttime.strftime("%Y%m%d-%H")  # str(starttime)[0:10]
  
  
  sim_name = PtoParam['sim_name']
  sim_duration = timedelta(days=int(PtoParam['cicoil']['sim_len']))
  particles_number = float(PtoParam['cicoil']['N_parti'])
  step_time = float(PtoParam['cicoil']['step_time'])    # hours
  output_step_time = float(PtoParam['cicoil']['repo_time'])    # hours
  release_points = np.int(1)
  
  seed_duration = endtime - starttime
    
  # Create and configure OpenCiceseOil
  weathering=PtoParam['model']['weathering']
  fartype=PtoParam['model']['fartype']

  # o = OpenCiceseOil(loglevel=20, weathering_model=weathering)
  o = OceanDrift(loglevel=20)
 # if fartype == '2D Sim.':
 #     o.disable_vertical_motion()
 # else:
 #     o.set_config('processes:dispersion', False)
  
  #### ADDING VARIABLE ALIASES AND FALLBACK VALUES TO THE BASEREADER
  list = br.variable_aliases
  list.update(dict([('AFAI (Alternative Floating Algae Index)', 'Sarg'), ('sea_surface_elevation', 'surf_el'), 
                  ('Water Surface Elevation', 'surf_el'), ('eastward_wind', 'x_wind'),
                  ('northward_wind', 'y_wind'),
                  ('eastward_wind', 'x_wind'),
                  ('northward_wind', 'y_wind')]))
  br.variable_aliases = list
  list = br.xy2eastnorth_mapping
  list.update(dict([('x_wind', ['eastward_wind', 'eastward_wind']),
                  ('y_wind', ['northward_wind', 'northward_wind'])]))
  br.xy2eastnorth_mapping = list

 
  o.set_config('drift:advection_scheme',PtoParam['model']['advection_scheme'])#agregado Ang   
  o._set_config_default('drift:current_uncertainty', 0.0)
  o._set_config_default('drift:wind_uncertainty', 0.0)
  
  
  sargtime = datetime(2022, 4, 20, 12, 0, 0)
  ds = xr.open_dataset('https://cwcgom.aoml.noaa.gov/thredds/dodsC/AFAI/USFAFAI7D.nc')
  corte = ds.AFAI.sel(time=sargtime, lon=slice(-95, -72))
  [b, c] = np.where(corte > 0.0035)   #### Adjust this filter to change particle number.. MAX concentration = 0.004
  [lat, lon] = [corte.lat[b], corte.lon[c]]
    
  
    # Readers
   # READERS
  if PtoParam['input']['curr'] == 'fnmoc':
       reader_current = reader_netCDF_CF_generic.Reader(filename=PtoParam['datadir'] + 'fnmoc-amseas/' + txtTime[0:8] + '/fnmoc-amseas-forecast-GoM-' + txtTime[0:8] + '-time*.nc', name='amseas_forecast')
  elif PtoParam['input']['curr'] == 'hycom':
       reader_current = reader_netCDF_CF_generic.Reader(filename=PtoParam['datadir'] + 'hycom/HYCOM-forecast-GoM-' + txtTime[0:8] + '.nc', name='hycom_forecast')
  if PtoParam['input']['wind'] == 'gfs':
       reader_winds = reader_netCDF_CF_generic.Reader(filename=PtoParam['datadir'] + 'gfs-winds/' + 'gfs-winds-forecast-GoM-' + txtTime[0:8] + '.nc', name='gfs_forecast')
   

   # o.add_reader([reader_basemap, reader_globcurrent, reader_oceanwind])
  o.add_reader([reader_current, reader_winds])
  
  
  o.seed_elements(lon, lat, time=starttime,z=0) 
  reader_current.buffer = 9
  output_file = output_path + '/' + PtoParam['point']['name'] + '_' +sim_name + '_' + starttime.strftime("%Y%m%d-%H") + '_' + endtime.strftime("%Y%m%d-%H") + '.nc'

  o.run(duration=sim_duration,
            time_step=timedelta(hours=step_time),
            time_step_output=timedelta(hours=output_step_time),
            outfile=output_file)
  #####
  
 
  
  print(o)
  
  # Post processing
  figs_path = ''.join((output_path,'/Figures/'))
  try:
      os.mkdir(figs_path) 
  except OSError as error:
      print(error)

  postp_file=''.join((figs_path,PtoParam['point']['name'], '_', sim_name,'_',starttime.strftime("%Y%m%d-%H")))

  # MAP
  o.plot(filename=postp_file +'_trayectorias.png')
   # Animations
  o.animation(fps=8, filename=postp_file + '.gif')
  
  

