package housing;

import collectors.HouseholdStats;
import collectors.HousingMarketStats;
import collectors.MicroDataRecorder;
import org.apache.commons.math3.random.MersenneTwister;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.io.File;
import java.lang.reflect.Field;
import java.lang.reflect.Method;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.ArrayList;

import static org.junit.jupiter.api.Assertions.assertAll;
import static org.junit.jupiter.api.Assertions.assertEquals;

class HouseholdAccountingTest {

    private static final String CONFIG_PATH = Paths.get("src/main/resources/config.properties")
            .toAbsolutePath().toString();

    @TempDir
    Path tempDir;

    @BeforeEach
    void setUp() {
        Model.config = new Config(CONFIG_PATH);
        Model.prng = new MersenneTwister(123);
        Model.government = new Government();
        Model.householdStats = new HouseholdStats();
        Model.householdStats.init();
    }

    @Test
    void recordedNonHousingConsumptionUsesUkEssentialConsumptionRule() throws Exception {
        Model.config.ESSENTIAL_CONSUMPTION_FRACTION = 0.5;
        Model.config.GOVERNMENT_MONTHLY_INCOME_SUPPORT = 800.0;

        Household household = new Household(Model.prng, 35.0);
        setField(household, "desiredConsumption", 250.0);

        assertEquals(650.0, household.getRecordedNonHousingConsumption(), 1.0e-9);
    }

    @Test
    void recordHousingCashFlowsSplitsRentalInterestAndPrincipal() throws Exception {
        Household household = new Household(Model.prng, 35.0);

        House rentalHome = new House(0);
        RentalAgreement rentalAgreement = new RentalAgreement();
        rentalAgreement.nPayments = 1;
        rentalAgreement.monthlyPayment = 900.0;
        household.getHousePayments().put(rentalHome, rentalAgreement);

        House ownedHome = new House(0);
        ownedHome.owner = household;
        MortgageAgreement mortgageAgreement = new MortgageAgreement(household, false);
        mortgageAgreement.nPayments = 12;
        mortgageAgreement.monthlyPayment = 1200.0;
        mortgageAgreement.principal = 200000.0;
        mortgageAgreement.monthlyInterestRate = 0.003;
        household.getHousePayments().put(ownedHome, mortgageAgreement);

        Method method = Household.class.getDeclaredMethod("recordHousingCashFlows");
        method.setAccessible(true);
        method.invoke(household);

        assertAll(
                () -> assertEquals(900.0, getDoubleField(Model.householdStats, "rentalCashOutflowCounter"), 1.0e-9),
                () -> assertEquals(600.0, getDoubleField(Model.householdStats, "mortgageInterestPaymentCounter"), 1.0e-9),
                () -> assertEquals(600.0, getDoubleField(Model.householdStats, "mortgagePrincipalPaymentCounter"), 1.0e-9)
        );
    }

    @Test
    void recordWritesBackwardCompatibleHousingWealthAndNewMicrodata() throws Exception {
        Model.config.recordHouseholdID = false;
        Model.config.recordEmploymentIncome = false;
        Model.config.recordRentalIncome = false;
        Model.config.recordBankBalance = false;
        Model.config.recordHousingWealth = true;
        Model.config.recordTotalDebt = true;
        Model.config.recordNHousesOwned = false;
        Model.config.recordHousingStatus = true;
        Model.config.recordAge = false;
        Model.config.recordConsumption = true;
        Model.config.recordSavingRate = false;
        Model.config.ESSENTIAL_CONSUMPTION_FRACTION = 0.25;
        Model.config.GOVERNMENT_MONTHLY_INCOME_SUPPORT = 400.0;

        Model.t = 996;
        Model.households = new ArrayList<>();
        Model.housingMarketStats = new FixedHousingMarketStats(250000.0);
        Model.microDataRecorder = new MicroDataRecorder(tempDir.toString() + File.separator);
        Model.microDataRecorder.openSingleRunSingleVariableFiles(1, false, false, false, false, true, true,
                false, true, false, true, false);

        Household household = new Household(Model.prng, 35.0);
        setField(household, "bankBalance", 5000.0);
        setField(household, "desiredConsumption", 250.0);
        setBehaviourPropertyInvestor(household, false);

        House home = new House(0);
        home.owner = household;
        home.resident = household;
        setField(household, "home", home);

        MortgageAgreement mortgageAgreement = new MortgageAgreement(household, false);
        mortgageAgreement.nPayments = 12;
        mortgageAgreement.monthlyPayment = 1200.0;
        mortgageAgreement.principal = 100000.0;
        mortgageAgreement.monthlyInterestRate = 0.003;
        household.getHousePayments().put(home, mortgageAgreement);

        Model.households.add(household);

        Model.householdStats.record();
        Model.microDataRecorder.finishRun(false, false, false, false, true, true,
                false, true, false, true, false);

        assertAll(
                () -> assertEquals("996; 150000.00",
                        Files.readString(tempDir.resolve("HousingWealth-run1.csv")).trim()),
                () -> assertEquals("996; 100000.00",
                        Files.readString(tempDir.resolve("TotalDebt-run1.csv")).trim()),
                () -> assertEquals("996; 2",
                        Files.readString(tempDir.resolve("HousingStatus-run1.csv")).trim()),
                () -> assertEquals("996; 350.00",
                        Files.readString(tempDir.resolve("NonHousingConsumption-run1.csv")).trim())
        );
    }

    private static void setBehaviourPropertyInvestor(Household household, boolean value) throws Exception {
        Field investorField = household.behaviour.getClass().getDeclaredField("BTLInvestor");
        investorField.setAccessible(true);
        investorField.setBoolean(household.behaviour, value);
    }

    private static void setField(Object target, String fieldName, Object value) throws Exception {
        Field field = target.getClass().getDeclaredField(fieldName);
        field.setAccessible(true);
        field.set(target, value);
    }

    private static double getDoubleField(Object target, String fieldName) throws Exception {
        Field field = target.getClass().getDeclaredField(fieldName);
        field.setAccessible(true);
        return field.getDouble(target);
    }

    private static final class FixedHousingMarketStats extends HousingMarketStats {
        private final double houseValue;

        private FixedHousingMarketStats(double houseValue) {
            super(null, 1);
            this.houseValue = houseValue;
        }

        @Override
        public double getExpAvSalePriceForQuality(int quality) {
            return houseValue;
        }
    }
}
