import numpy as np
import lightkurve as lk
import matplotlib.pyplot as plt

def fetch_and_clean_raw_data(target_id: str):
    """Phase 1 & Phase 2A: Fetching and removing NaNs"""
    search_result = lk.search_lightcurve(target_id, mission="Kepler")
    if len(search_result) == 0:
        return None
    
    # Instead of pulling raw arrays immediately, we keep it as a LightCurve object 
    # for one more step so we can use Lightkurve's advanced math utilities.
    lc = search_result[0].download()
    return lc.remove_nans()


def advanced_transformation_pipeline(lc):
    """
    Phase 2B: Detrending & Final Flattening
    Removes long-term telescope drift to isolate the pure physics of the transits.
    """
    print("\nExecuting advanced ETL transformations (Detrending)...")
    
    # Flatten uses a rolling Savitzky-Golay filter under the hood.
    # window_length=101 means it looks at a rolling window of 101 data points 
    # to find the slow instrument curve, then divides the data by it.
    flattened_lc = lc.flatten(window_length=101)
    
    # Extract clean, pristine, flat NumPy arrays
    final_time = flattened_lc.time.value
    final_flux = flattened_lc.flux.value
    
    return final_time, final_flux


if __name__ == "__main__":
    TARGET_KIC = "Kepler-8"
    
    # 1. Ingest & clean basic NaNs
    lc_object = fetch_and_clean_raw_data(TARGET_KIC)
    
    if lc_object is not None:
        # 2. Advanced ETL transformation (Flattening the drift)
        time, flux = advanced_transformation_pipeline(lc_object)
        
        # 3. Re-verify visually
        print("\nDisplaying detrended dataset...")
        plt.figure(figsize=(12, 5))
        plt.plot(time, flux, 'b.', markersize=1, alpha=0.6) # Switch to blue to mark our progress
        plt.title(f"Pristine Flattened Light Curve - {TARGET_KIC}")
        plt.xlabel("Time (BKJD)")
        plt.ylabel("Normalized Flux")
        plt.ylim(0.98, 1.02)
        plt.grid(True, linestyle='--', alpha=0.5)
        plt.show()