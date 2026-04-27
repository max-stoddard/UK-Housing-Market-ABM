package data;

import housing.Model;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import utilities.BinnedDataDouble;

import java.lang.reflect.Method;
import java.nio.file.Path;

import static org.junit.jupiter.api.Assertions.assertEquals;

class DemographicsTest {

    @TempDir
    Path tempDir;

    @BeforeAll
    static void setUpModelConfig() {
        new Model("src/main/resources/config.properties", "tmp/demographics-test/");
    }

    @Test
    void variableWidthAgeDistributionTransformsToMonthlySupport() throws Exception {
        BinnedDataDouble data = new BinnedDataDouble(16.0, 4.0);
        data.add(0.02);
        data.add(0.03);
        data.add(0.01);
        setExplicitEdges(data, new double[][]{
                {16.0, 20.0},
                {20.0, 25.0},
                {25.0, 35.0},
        });

        BinnedDataDouble monthly = transformAgeDistributionToMonthly(data);

        assertEquals(16.0, monthly.getSupportLowerBound(), 1.0e-12);
        assertEquals(35.0, monthly.getSupportUpperBound(), 1.0e-12);
        assertEquals((35 - 16)*12, monthly.size());
        assertEquals(1.0, integrate(monthly), 1.0e-9);
    }

    @Test
    void equalWidthAgeDistributionMatchesLegacyTransform() throws Exception {
        BinnedDataDouble data = new BinnedDataDouble(15.0, 10.0);
        data.add(0.001);
        data.add(0.010);
        data.add(0.020);
        data.add(0.015);

        BinnedDataDouble monthly = transformAgeDistributionToMonthly(data);
        BinnedDataDouble legacy = legacyTransformAgeDistributionToMonthly(data);

        assertEquals(legacy.size(), monthly.size());
        assertEquals(legacy.getSupportLowerBound(), monthly.getSupportLowerBound(), 1.0e-12);
        assertEquals(legacy.getSupportUpperBound(), monthly.getSupportUpperBound(), 1.0e-12);
        for (int i = 0; i < legacy.size(); i++) {
            assertEquals(legacy.get(i), monthly.get(i), 1.0e-12);
        }
    }

    private static BinnedDataDouble transformAgeDistributionToMonthly(BinnedDataDouble data) throws Exception {
        Method method = Demographics.class.getDeclaredMethod("transformAgeDistributionToMonthly", BinnedDataDouble.class);
        method.setAccessible(true);
        return (BinnedDataDouble) method.invoke(null, data);
    }

    private static void setExplicitEdges(BinnedDataDouble data, double[][] edges) throws Exception {
        java.lang.reflect.Field lowerField = BinnedDataDouble.class.getDeclaredField("binLowerEdges");
        java.lang.reflect.Field upperField = BinnedDataDouble.class.getDeclaredField("binUpperEdges");
        lowerField.setAccessible(true);
        upperField.setAccessible(true);
        java.util.ArrayList<Double> lowerEdges = new java.util.ArrayList<>();
        java.util.ArrayList<Double> upperEdges = new java.util.ArrayList<>();
        for (double[] edge : edges) {
            lowerEdges.add(edge[0]);
            upperEdges.add(edge[1]);
        }
        lowerField.set(data, lowerEdges);
        upperField.set(data, upperEdges);
    }

    private static double integrate(BinnedDataDouble data) {
        double total = 0.0;
        for (int i = 0; i < data.size(); i++) {
            total += data.get(i) * data.getBinWidth(i);
        }
        return total;
    }

    private static BinnedDataDouble legacyTransformAgeDistributionToMonthly(BinnedDataDouble ageDistribution) {
        BinnedDataDouble monthlyAgeDistribution = new BinnedDataDouble(
                ageDistribution.getSupportLowerBound(),
                1.0 / Model.config.constants.MONTHS_IN_YEAR);
        int minAge = (int)ageDistribution.getSupportLowerBound();
        int maxAge = (int)ageDistribution.getSupportUpperBound();
        double[] binCenters = new double[ageDistribution.size()];
        for (int i = 0; i < ageDistribution.size(); i++) {
            binCenters[i] = minAge + ageDistribution.getBinWidth() / 2.0 + i * ageDistribution.getBinWidth();
        }
        double[] monthlyBinCenters = new double[(maxAge - minAge) * Model.config.constants.MONTHS_IN_YEAR];
        for (int i = 0; i < monthlyBinCenters.length; i++) {
            monthlyBinCenters[i] = minAge + monthlyAgeDistribution.getBinWidth() / 2.0
                    + i * monthlyAgeDistribution.getBinWidth();
        }
        int[] whichBin = legacyComputeWhichBin(monthlyBinCenters, binCenters);
        double[][] slopesAndIntercepts = legacyComputeSlopesAndIntercepts(binCenters, ageDistribution);
        double[] slopes = slopesAndIntercepts[0];
        double[] intercepts = slopesAndIntercepts[1];
        for (int i = 0; i < monthlyBinCenters.length; i++) {
            double density = slopes[whichBin[i]] * monthlyBinCenters[i] + intercepts[whichBin[i]];
            monthlyAgeDistribution.add(Math.max(density, 0.0));
        }
        double factor = integrate(monthlyAgeDistribution);
        for (int i = 0; i < monthlyAgeDistribution.size(); i++) {
            monthlyAgeDistribution.set(i, monthlyAgeDistribution.get(i) / factor);
        }
        return monthlyAgeDistribution;
    }

    private static double[][] legacyComputeSlopesAndIntercepts(double[] binCenters, BinnedDataDouble ageDistribution) {
        double[] slopes = new double[binCenters.length + 1];
        double[] intercepts = new double[binCenters.length + 1];
        for (int i = 1; i < binCenters.length; i++) {
            slopes[i] = (ageDistribution.getBinAt(binCenters[i]) - ageDistribution.getBinAt(binCenters[i - 1]))
                    / (binCenters[i] - binCenters[i - 1]);
            intercepts[i] = ageDistribution.getBinAt(binCenters[i]) - slopes[i] * binCenters[i];
        }
        slopes[0] = slopes[1];
        intercepts[0] = intercepts[1];
        slopes[slopes.length - 1] = slopes[slopes.length - 2];
        intercepts[intercepts.length - 1] = intercepts[intercepts.length - 2];
        return new double[][]{slopes, intercepts};
    }

    private static int[] legacyComputeWhichBin(double[] shortEdges, double[] longEdges) {
        int[] whichBin = new int[shortEdges.length];
        int i = 0;
        int j = 0;
        for (double threshold : longEdges) {
            while (j < shortEdges.length && shortEdges[j] < threshold) {
                whichBin[j] = i;
                j++;
            }
            i++;
        }
        while (j < shortEdges.length) {
            whichBin[j] = i;
            j++;
        }
        return whichBin;
    }
}

