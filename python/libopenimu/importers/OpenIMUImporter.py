from libopenimu.importers.BaseImporter import BaseImporter
from libopenimu.models.sensor_types import SensorType
from libopenimu.models.units import Units
from libopenimu.models.Recordset import Recordset
from libopenimu.models.SensorTimestamps import SensorTimestamps
from libopenimu.models.data_formats import DataFormat
from libopenimu.tools.timing import timing
from libopenimu.db.DBManager import DBManager
from libopenimu.models.Participant import Participant
from libopenimu.importers.wimu import GPSGeodetic

import numpy as np
import math
import datetime

import struct
import sys
import binascii
import datetime
import string


class OpenIMUImporter(BaseImporter):
    def __init__(self, manager: DBManager, participant: Participant):
        super().__init__(manager, participant)
        # print('OpenIMU Importer')
        # No recordsets when starting
        self.recordsets = []

    def get_recordset(self, start_timestamp, end_timestamp):
        my_start_time = datetime.datetime.fromtimestamp(start_timestamp)
        my_end_time = datetime.datetime.fromtimestamp(end_timestamp)

        # Find a record the same day
        for record in self.recordsets:
            # Same date return this record
            if record.start_timestamp.date() == my_start_time.date():
                # Update start and stop
                if my_start_time < record.start_timestamp:
                    record.start_timestamp = my_start_time
                if my_end_time > record.end_timestamp:
                    record.end_timestamp = my_end_time
                return record

        # Return new record
        recordset = self.db.add_recordset(self.participant, str(my_start_time.date()), my_start_time, my_end_time)
        self.recordsets.append(recordset)
        return recordset

    @timing
    def load(self, filename):
        # print('OpenIMUImporter.load')
        results = {}
        with open(filename, "rb") as file:
            print('Loading File: ', filename)
            results = self.readDataFile(file, False)

        print('Done!')
        return results

    @timing
    def import_imu_to_database(self, timestamp, sample_rate, sensors, channels, recordset, data: dict):
        # print('import_imu_to_database')
        values = np.array(data['values'], dtype=np.float32)

        if len(values) == 0:
            return False

        # print("Values shape: ", values.shape)
        end_timestamp = np.floor(data['end_time'])

        # Update end_timestamp if required
        if end_timestamp > recordset.end_timestamp.timestamp():
            recordset.end_timestamp = datetime.datetime.fromtimestamp(end_timestamp)

        # Create sensor timestamps first
        sensor_timestamps = SensorTimestamps()
        sensor_timestamps.timestamps = data['times']
        sensor_timestamps.update_timestamps()

        # Acc
        for i in range(len(channels['acc'])):
            self.add_sensor_data_to_db(recordset, sensors['acc'], channels['acc'][i],
                                       sensor_timestamps, values[:, i])

        # Gyro
        for i in range(len(channels['gyro'])):
            self.add_sensor_data_to_db(recordset, sensors['gyro'], channels['gyro'][i],
                                       sensor_timestamps, values[:, i + 3])

        # Magnetometer
        for i in range(len(channels['mag'])):
            self.add_sensor_data_to_db(recordset, sensors['mag'], channels['mag'][i],
                                       sensor_timestamps, values[:, i + 6])

        self.db.commit()

        return True

    @timing
    def import_power_to_database(self, timestamp, sensors, channels, recordset, data: dict):

        # print('import_imu_to_database')
        values = np.array(data['values'], dtype=np.float32)

        if len(values) == 0:
            return False

        # Create sensor timestamps first
        sensor_timestamps = SensorTimestamps()
        sensor_timestamps.timestamps = data['times']
        sensor_timestamps.update_timestamps()

        self.add_sensor_data_to_db(recordset, sensors['battery'], channels['battery'],
                                   sensor_timestamps, values[:, 0])

        self.add_sensor_data_to_db(recordset, sensors['current'], channels['current'],
                                   sensor_timestamps, values[:, 1])

        self.db.commit()

        return True

    @timing
    def import_gps_to_database(self, timestamp, sensors, channels, recordset, data: dict):

        # print('import_imu_to_database')
        values = np.array(data['values'], dtype=np.float32)

        if len(values) == 0:
            return False

        # Regenerate GPS data to be stored in the DB as SIRF data
        # TODO Better GPS solution?

        # We have one sample per second of GPS data
        for i in range(len(values)):
            val = values[i]
            geo = GPSGeodetic()
            # Discard invalid data
            if math.isnan(val[1]) or math.isnan(val[2]):
                continue

            geo.latitude = val[1] * 1e7
            geo.longitude = val[2] * 1e7
            # altitude = val[3] * 1e7

            # Create sensor timestamps first
            sensor_timestamps = SensorTimestamps()
            sensor_timestamps.timestamps = data['times'][i:i+1]
            sensor_timestamps.update_timestamps()

            self.add_sensor_data_to_db(recordset, sensors['gps'], channels['gps'],
                                       sensor_timestamps, geo)

        # Commit to file
        self.db.commit()

        return True

    @timing
    def import_baro_to_database(self,  timestamp, sensors, channels, recordset, data: list):
        # print('import_imu_to_database')
        values = np.array(data['values'], dtype=np.float32)

        if len(values) == 0:
            return False

        # Create sensor timestamps first
        sensor_timestamps = SensorTimestamps()
        sensor_timestamps.timestamps = data['times']
        sensor_timestamps.update_timestamps()

        self.add_sensor_data_to_db(recordset, sensors['baro'], channels['baro'],
                                   sensor_timestamps, values[:, 1])

        # Commit to file
        self.db.commit()

        return True

    def create_sensor_and_channels(self, sample_rate):
        # Baro
        baro_sensor = self.add_sensor_to_db(SensorType.BAROMETER, 'Barometer',
                                            'OpenIMU-HW',
                                            'Unknown', 1, 1)

        baro_channel = self.add_channel_to_db(baro_sensor, Units.KPA,
                                              DataFormat.FLOAT32, 'Pressure')

        # Battery
        battery_sensor = self.add_sensor_to_db(SensorType.BATTERY, 'Battery',
                                                     'OpenIMU-HW',
                                                     'Unknown', 1, 1)

        battery_channel = self.add_channel_to_db(battery_sensor, Units.VOLTS,
                                                 DataFormat.FLOAT32, 'Voltage')

        # Current
        current_sensor = self.add_sensor_to_db(SensorType.CURRENT, 'Current',
                                                     'OpenIMU-HW',
                                                     'Unknown', 1, 1)

        current_channel = self.add_channel_to_db(current_sensor, Units.AMPERES,
                                                 DataFormat.FLOAT32, 'Current')

        # GPS
        gps_sensor = self.add_sensor_to_db(SensorType.GPS, 'GPS',
                                            'OpenIMU-HW',
                                            'Unknown', 1, 1)

        gps_channel = self.add_channel_to_db(gps_sensor, Units.NONE,
                                              DataFormat.UINT8, 'GPS_SIRF')

        # Accelerometers
        accelerometer_sensor = self.add_sensor_to_db(SensorType.ACCELEROMETER, 'Accelerometer',
                                                     'OpenIMU-HW',
                                                     'Unknown', sample_rate, 1)

        accelerometer_channels = list()

        # Create channels
        accelerometer_channels.append(self.add_channel_to_db(accelerometer_sensor, Units.GRAVITY_G,
                                                             DataFormat.FLOAT32, 'Accelerometer_X'))

        accelerometer_channels.append(self.add_channel_to_db(accelerometer_sensor, Units.GRAVITY_G,
                                                             DataFormat.FLOAT32, 'Accelerometer_Y'))

        accelerometer_channels.append(self.add_channel_to_db(accelerometer_sensor, Units.GRAVITY_G,
                                                             DataFormat.FLOAT32, 'Accelerometer_Z'))

        # Gyro
        gyro_sensor = self.add_sensor_to_db(SensorType.GYROMETER, 'Gyro',
                                            'OpenIMU-HW',
                                            'Unknown', sample_rate, 1)

        gyro_channels = list()

        # Create channels
        gyro_channels.append(self.add_channel_to_db(gyro_sensor, Units.DEG_PER_SEC,
                                                    DataFormat.FLOAT32, 'Gyro_X'))

        gyro_channels.append(self.add_channel_to_db(gyro_sensor, Units.DEG_PER_SEC,
                                                    DataFormat.FLOAT32, 'Gyro_Y'))

        gyro_channels.append(self.add_channel_to_db(gyro_sensor, Units.DEG_PER_SEC,
                                                    DataFormat.FLOAT32, 'Gyro_Z'))

        # Magnetometer
        mag_sensor = self.add_sensor_to_db(SensorType.MAGNETOMETER, 'Magnetometer',
                                           'OpenIMU-HW',
                                           'Unknown', sample_rate, 1)

        mag_channels = list()

        # Create channels
        mag_channels.append(self.add_channel_to_db(mag_sensor, Units.UTESLA,
                                                   DataFormat.FLOAT32, 'Mag_X'))

        mag_channels.append(self.add_channel_to_db(mag_sensor, Units.UTESLA,
                                                   DataFormat.FLOAT32, 'Mag_Y'))

        mag_channels.append(self.add_channel_to_db(mag_sensor, Units.UTESLA,
                                                   DataFormat.FLOAT32, 'Mag_Z'))

        # Commit to DB
        self.db.commit()

        # Create sensor and channels dict
        sensors = {'acc': accelerometer_sensor,
                   'gyro': gyro_sensor,
                   'mag': mag_sensor,
                   'battery': battery_sensor,
                   'current': current_sensor,
                   'gps': gps_sensor,
                   'baro': baro_sensor}

        channels = {'acc': accelerometer_channels,
                    'gyro': gyro_channels,
                    'mag': mag_channels,
                    'battery': battery_channel,
                    'current': current_channel,
                    'gps': gps_channel,
                    'baro': baro_channel}

        return sensors, channels

    @timing
    def import_to_database(self, result):
        print('OpenIMUImporter.import_to_database')

        # TODO use configuration, hardcoded for now
        sample_rate = 50

        # First create all sensors and channels
        sensors, channels = self.create_sensor_and_channels(sample_rate)

        # Timestamps are hour aligned
        for timestamp in result:
            if result[timestamp].__contains__('imu'):
                # print('contains imu')
                recordset = self.get_recordset(result[timestamp]['imu']['start_time'],
                                               result[timestamp]['imu']['end_time'])

                if not self.import_imu_to_database(timestamp, sample_rate, sensors,
                                                   channels, recordset, result[timestamp]['imu']):
                    print('IMU import error')
            if result[timestamp].__contains__('power'):
                # print('contains power')
                recordset = self.get_recordset(result[timestamp]['power']['start_time'],
                                               result[timestamp]['power']['start_time'])

                if not self.import_power_to_database(timestamp, sensors, channels, recordset,
                                                     result[timestamp]['power']):
                    print('Power import error')
            if result[timestamp].__contains__('gps'):
                # print('contains gps')
                recordset = self.get_recordset(result[timestamp]['gps']['start_time'],
                                               result[timestamp]['gps']['start_time'])

                if not self.import_gps_to_database(timestamp, sensors, channels, recordset,
                                                   result[timestamp]['gps']):
                    print('GPS import error')
            if result[timestamp].__contains__('baro'):
                # print('contains baro')
                recordset = self.get_recordset(result[timestamp]['baro']['start_time'],
                                               result[timestamp]['baro']['start_time'])

                if not self.import_baro_to_database(timestamp, sensors, channels, recordset,
                                                    result[timestamp]['baro']):
                    print('Baro import error')

        # Make sure everything is commited to DB
        self.db.commit()

    def processImuChunk(self, chunk, debug=False):
        data = struct.unpack("9f", chunk)
        if debug:
            print("IMU: ", data)
        return data

    def processTimestampChunk(self, chunk, debug=False):
        [timestamp] = struct.unpack("i", chunk)
        if debug:
            print(datetime.datetime.utcfromtimestamp(timestamp).strftime('%Y-%m-%d %H:%M:%S'))
        return timestamp

    def processGPSChunk(self, chunk, debug=False):
        data = struct.unpack("?3f", chunk)
        if debug:
            print("GPS: ", data)
        return data

    def processBarometerChunk(self, chunk, debug=False):
        data = struct.unpack("2f", chunk)
        if debug:
            print("BARO: ", data[0], data[1])
        return data

    def processPowerChunk(self, chunk, debug=False):
        data = struct.unpack("2f", chunk)
        if debug:
            print("POWER: ", data[0], data[1])
        return data

    def readDataFile(self, file, debug=False):
        n = 0
        results = {}
        timestamp_hour = None

        # Todo better than while 1?
        while file.readable():

            chunk = file.read(1)
            if len(chunk) < 1:
                print("Reached end of file")
                break

            (headChar) = struct.unpack("c", chunk)
            # print('headchar ', headChar)

            if headChar[0] == b'h':
                n = n + 1
                print("New log stream detected")
            elif headChar[0] == b't':
                n = n + 1
                chunk = file.read(struct.calcsize("i"))
                current_timestamp = self.processTimestampChunk(chunk, debug)

                timestamp_hour = np.floor(current_timestamp / 3600) * 3600

                # Initialize data structure at this timestamp
                if not results.__contains__(timestamp_hour):
                    # print("init timestamp = ", timestamp)
                    results[timestamp_hour] = {}
                    results[timestamp_hour]['gps'] = {'times': [], 'values': [],
                                                      'start_time': current_timestamp,
                                                      'end_time': current_timestamp + 1}

                    results[timestamp_hour]['power'] = {'times': [], 'values': [],
                                                        'start_time': current_timestamp,
                                                        'end_time': current_timestamp + 1}

                    results[timestamp_hour]['imu'] = {'times': [], 'values': [],
                                                      'start_time': current_timestamp,
                                                      'end_time': current_timestamp + 1}

                    results[timestamp_hour]['baro'] = {'times': [], 'values': [],
                                                       'start_time': current_timestamp,
                                                       'end_time': current_timestamp + 1}

            elif headChar[0] == b'i':
                n = n + 1
                chunk = file.read(struct.calcsize("9f"))
                data = self.processImuChunk(chunk, debug)
                if timestamp_hour is not None:
                    results[timestamp_hour]['imu']['values'].append(data)
                    results[timestamp_hour]['imu']['end_time'] = current_timestamp + 1

            elif headChar[0] == b'g':
                n = n + 1
                chunk = file.read(struct.calcsize("?3f"))
                data = self.processGPSChunk(chunk, debug)
                if timestamp_hour is not None:
                    results[timestamp_hour]['gps']['values'].append(data)
                    results[timestamp_hour]['gps']['end_time'] = current_timestamp + 1

            elif headChar[0] == b'p':
                n = n + 1
                chunk = file.read(struct.calcsize("2f"))
                data = self.processPowerChunk(chunk, debug)
                if timestamp_hour is not None:
                    results[timestamp_hour]['power']['values'].append(data)
                    results[timestamp_hour]['power']['end_time'] = current_timestamp + 1

            elif headChar[0] == b'b':
                n = n + 1
                chunk = file.read(struct.calcsize("2f"))
                data = self.processBarometerChunk(chunk, debug)
                if timestamp_hour is not None:
                    results[timestamp_hour]['baro']['values'].append(data)
                    results[timestamp_hour]['baro']['end_time'] = current_timestamp + 1

            else:
                print("Unrecognised chunk :", headChar[0])
                break

        # File is read.
        # Generate time according to number of samples per timestamp
        for timestamp in results:
            for key in results[timestamp]:
                # Generate time values
                timevect = np.linspace(results[timestamp][key]['start_time'],
                                       results[timestamp][key]['end_time'],
                                       num=len(results[timestamp][key]['values']),
                                       endpoint=False, dtype=np.float64)

                # print('key', key, len(results[timestamp][key]['values']), len(timevect))
                results[timestamp][key]['times'] = timevect
            # print('timestamp: ', timestamp)

        return results
